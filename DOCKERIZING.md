# Dockerizing the RLM Application

This document explains the complications of running this RLM application inside Docker, given that it programmatically spawns Docker containers itself (Docker-in-Docker).

## The Challenge

Our application uses Docker programmatically to create isolated Python execution environments. Each query spawns a new Docker container to safely execute LLM-generated code. This is a powerful pattern for agentic tools, but it creates complications when you want to dockerize the FastAPI application itself.

**Current architecture:**
```
[FastAPI on Host] → [Docker API] → [Spawns Python Container]
```

**Dockerized architecture:**
```
[FastAPI in Container] → [Docker API on Host] → [Spawns Python Container]
                      ↑
                Docker-in-Docker (DinD)
```

## Two Approaches to Docker-in-Docker

### 1. Docker Socket Mounting (Recommended)

Mount the host's Docker socket into your FastAPI container:

```yaml
# docker-compose.yml
version: '3.8'

services:
  rlm-api:
    build: .
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # Host Docker socket
      - ./uploads:/app/uploads                      # Shared upload directory
```

**How it works:**
- Your containerized FastAPI app communicates with the **host's** Docker daemon
- When it spawns Python containers, they're siblings on the host, not nested children
- All containers run at the same level in the host's Docker environment

**Pros:**
- Simple to set up
- Good performance (no nested virtualization)
- Standard pattern used by CI/CD tools (Jenkins, GitLab Runner)

**Cons:**
- Security risk: Container has full Docker control
- Path mapping complications (see below)

### 2. True Docker-in-Docker (Not Recommended)

Run a Docker daemon inside your container using the official `docker:dind` image.

**Why avoid this:**
- Complex setup requiring privileged mode
- Security concerns (privileged containers)
- Performance overhead
- Networking complications
- Storage driver issues

## Critical Issue: Volume Path Resolution

This is the **biggest gotcha** when dockerizing this application.

### The Problem

```python
# Currently in rlm_session.py:
abs_path = str(Path(self.document_path).resolve())
# Returns: /app/uploads/test.json (path inside FastAPI container)

self.container = self.client.containers.run(
    volumes={
        abs_path: {'bind': '/doc.json', 'mode': 'ro'}
        # ❌ FAILS! Docker daemon on host can't find /app/uploads/test.json
    }
)
```

**Why it fails:**
1. `document_path` resolves to `/app/uploads/test.json` inside the FastAPI container
2. But the Docker daemon runs on the **host**, which doesn't have `/app/uploads/`
3. The spawned Python container tries to mount a file that doesn't exist from the host's perspective
4. Result: `Error: no such file or directory`

### The Solution

You must translate container paths to host paths:

```python
# rlm_session.py
import os
from pathlib import Path

class REPLSession:
    def __init__(self, document_path: str):
        self.client = docker.from_env()
        self.document_path = document_path
        self.container = None
        self.init_code = """..."""

    def start(self):
        """Spin up isolated container with document mounted"""
        print(f"Starting REPL session with document: {self.document_path}")

        # Get host base path from environment
        host_base = os.getenv('HOST_UPLOAD_PATH')

        if host_base:
            # Running in Docker: translate container path to host path
            relative_path = Path(self.document_path).name  # Just filename
            host_abs_path = str(Path(host_base) / relative_path)
        else:
            # Running on host: use path as-is
            host_abs_path = str(Path(self.document_path).resolve())

        self.container = self.client.containers.run(
            'python:3.11-slim',
            command='sleep infinity',
            detach=True,
            mem_limit='512m',
            cpu_quota=50000,
            network_disabled=True,
            volumes={
                host_abs_path: {'bind': '/doc.json', 'mode': 'ro'}  # ✅ Host path
            }
        )

        print("✓ REPL session initialized")
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  rlm-api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ${PWD}/uploads:/app/uploads  # Mount uploads from host
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - HOST_UPLOAD_PATH=${PWD}/uploads  # ⚠️ Absolute host path
    restart: unless-stopped
```

## Other Complications

### 1. Security Concerns

Mounting the Docker socket gives the container **complete control** over Docker:

**What the container can do:**
- ✅ Spawn any container with any privileges
- ✅ Mount any host filesystem path
- ✅ Access other containers' filesystems
- ✅ Stop, remove, or modify other containers
- ✅ Effectively escape container isolation

**Mitigation strategies:**

#### Option A: Docker Socket Proxy
Use `tecnativa/docker-socket-proxy` to restrict API access:

```yaml
version: '3.8'

services:
  docker-proxy:
    image: tecnativa/docker-socket-proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - CONTAINERS=1     # Allow container operations
      - IMAGES=1         # Allow image operations
      - POST=1           # Allow POST requests
      - DELETE=1         # Allow DELETE requests
      - NETWORKS=0       # Deny network operations
      - VOLUMES=0        # Deny volume operations
      - SERVICES=0       # Deny service operations
    networks:
      - docker-proxy-net

  rlm-api:
    build: .
    environment:
      - DOCKER_HOST=tcp://docker-proxy:2375  # Use proxy, not socket
    depends_on:
      - docker-proxy
    networks:
      - docker-proxy-net

networks:
  docker-proxy-net:
```

#### Option B: AppArmor/SELinux Policies
Restrict what the container can do with the socket.

#### Option C: Accept the Risk (POC Only)
Document that this is a development/POC setup and should not be exposed to untrusted users.

### 2. Network Complexity

```python
# Spawned containers are on a different network than the FastAPI container
# If they needed to communicate (they don't currently), you'd need:

self.container = self.client.containers.run(
    # ...
    network='rlm-network'  # Shared network
)
```

```yaml
# docker-compose.yml
services:
  rlm-api:
    networks:
      - rlm-network

networks:
  rlm-network:
    driver: bridge
```

### 3. Cleanup on Crash

If the FastAPI container crashes, spawned Python containers might not be cleaned up.

**Solution: Orphan cleanup on startup**

```python
# In main.py, add to lifespan startup:

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup - cleanup orphaned containers
    cleanup_orphan_containers()

    yield

    # Shutdown - clean up all sessions
    for doc_id in list(active_sessions.keys()):
        active_sessions[doc_id]['session'].cleanup()


def cleanup_orphan_containers():
    """Remove any leftover RLM containers from previous crashes"""
    try:
        client = docker.from_env()
        for container in client.containers.list(all=True):
            # Use container labels to identify RLM containers
            labels = container.labels
            if labels.get('app') == 'rlm-poc':
                print(f"Cleaning up orphaned container: {container.id[:12]}")
                container.remove(force=True)
    except Exception as e:
        print(f"Warning: Could not cleanup orphans: {e}")
```

**Update REPLSession to use labels:**

```python
self.container = self.client.containers.run(
    'python:3.11-slim',
    # ...
    labels={
        'app': 'rlm-poc',
        'doc_id': doc_id,
        'created_at': datetime.utcnow().isoformat()
    }
)
```

### 4. Image Availability

The `python:3.11-slim` image must be available on the host, not inside the FastAPI container.

**Solution: Pre-pull in Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Docker CLI
RUN apt-get update && \
    apt-get install -y docker.io && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-pull the image used for REPL sessions
# This happens at build time, so the image is cached on the host
RUN docker pull python:3.11-slim || true

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Note:** The `docker pull` in Dockerfile won't work without special build setup. Instead, document that users should pre-pull:

```bash
docker pull python:3.11-slim
docker-compose up
```

## Complete Docker Setup Example

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Docker CLI to communicate with host daemon
RUN apt-get update && \
    apt-get install -y --no-install-recommends docker.io && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  rlm-api:
    build: .
    container_name: rlm-poc-api
    ports:
      - "8000:8000"
    volumes:
      # Mount Docker socket for spawning containers
      - /var/run/docker.sock:/var/run/docker.sock
      # Mount uploads directory (must be absolute path on host)
      - ${PWD}/uploads:/app/uploads
    environment:
      # Anthropic API key from .env file
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      # Host path for volume mounting (same as volume mount above)
      - HOST_UPLOAD_PATH=${PWD}/uploads
    restart: unless-stopped
    networks:
      - rlm-network

networks:
  rlm-network:
    driver: bridge
```

### .env

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Usage

```bash
# Pull required image first
docker pull python:3.11-slim

# Start the service
docker-compose up -d

# Test the API
curl -X POST "http://localhost:8000/upload" -F "file=@test_financial.json"
curl -X POST "http://localhost:8000/query" \
  -F "doc_id=test_financial" \
  -F "query=What was the Q3 revenue?"

# Stop the service
docker-compose down
```

## Alternatives to Docker-in-Docker

If DinD feels too complex or risky for your use case, consider these alternatives:

### 1. Keep FastAPI on Host (Recommended for POC)

**Pros:**
- Simplest setup
- No path mapping issues
- No security concerns with Docker socket
- Easy debugging

**Cons:**
- Not containerized
- Requires Python/Docker on host

**When to use:** POCs, development, small-scale deployments

### 2. Kubernetes Jobs

Instead of Docker containers, use Kubernetes Jobs:

```python
from kubernetes import client, config

def execute_code(self, code: str):
    config.load_incluster_config()
    batch_api = client.BatchV1Api()

    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=f"rlm-job-{uuid.uuid4().hex[:8]}"),
        spec=client.V1JobSpec(
            template=client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="repl",
                            image="python:3.11-slim",
                            command=["python", "-c", code]
                        )
                    ],
                    restart_policy="Never"
                )
            )
        )
    )

    batch_api.create_namespaced_job(namespace="default", body=job)
```

**Pros:**
- Native Kubernetes resource management
- Better multi-tenant isolation
- Scales horizontally
- No DinD complexity

**Cons:**
- Requires Kubernetes cluster
- More complex orchestration

### 3. Serverless Functions

Use AWS Lambda, Google Cloud Functions, or similar:

```python
import boto3

def execute_code(self, code: str):
    lambda_client = boto3.client('lambda')

    response = lambda_client.invoke(
        FunctionName='rlm-code-executor',
        InvocationType='RequestResponse',
        Payload=json.dumps({'code': code, 'document': doc_data})
    )

    return json.loads(response['Payload'].read())
```

**Pros:**
- No infrastructure management
- Auto-scaling
- Pay per execution
- No DinD concerns

**Cons:**
- Vendor lock-in
- Cold start latency
- Execution time limits
- Cost at scale

### 4. Separate Worker Pool

Run dedicated Python worker processes, communicate via message queue:

```
[FastAPI] → [Redis/RabbitMQ Queue] → [Worker Pool] → [Results]
```

```python
# In FastAPI
import redis
r = redis.Redis()

def execute_code(self, code: str):
    job_id = str(uuid.uuid4())
    r.lpush('code_queue', json.dumps({'id': job_id, 'code': code}))

    # Poll for result
    while True:
        result = r.get(f'result:{job_id}')
        if result:
            return json.loads(result)
        time.sleep(0.1)
```

```python
# Worker process
while True:
    job = r.brpop('code_queue')
    job_data = json.loads(job[1])
    result = exec(job_data['code'])
    r.set(f'result:{job_data["id"]}', json.dumps(result))
```

**Pros:**
- Clean separation of concerns
- Workers can run anywhere
- Easy to scale workers independently
- No Docker-in-Docker

**Cons:**
- Additional infrastructure (Redis/RabbitMQ)
- More complex architecture
- Workers still need sandboxing

### 5. gVisor or Firecracker

Lighter-weight sandboxing without full Docker:

- **gVisor**: User-space kernel for containers
- **Firecracker**: Micro-VMs for serverless

**Pros:**
- Better security isolation
- Faster startup than Docker
- Lower overhead

**Cons:**
- More complex setup
- Less mature ecosystem
- Platform-specific

## Recommendations by Use Case

### For this POC (Current State)
**Recommendation:** Keep FastAPI on host

```bash
# No Docker for FastAPI
uvicorn main:app --reload
```

**Why:** Simplest, no path issues, easy debugging

### For Production (Small Scale)
**Recommendation:** Docker Compose with socket mounting + security proxy

```yaml
services:
  docker-proxy:
    image: tecnativa/docker-socket-proxy
    # ... (see security section above)

  rlm-api:
    build: .
    environment:
      - DOCKER_HOST=tcp://docker-proxy:2375
```

**Why:** Containerized, manageable security tradeoffs, good enough for trusted users

### For Production (Large Scale)
**Recommendation:** Kubernetes + Separate Worker Pool

```
[Ingress] → [FastAPI Pods] → [Redis] → [Worker Pods with gVisor]
```

**Why:** Scales horizontally, proper isolation, production-grade observability

### For Serverless
**Recommendation:** AWS Lambda or Cloud Functions

**Why:** No infrastructure management, auto-scaling, pay-per-use

## Summary

Dockerizing this application introduces Docker-in-Docker complexity, with the **path mapping issue** being the most critical challenge. For a POC, running FastAPI directly on the host is simplest. For production, use Kubernetes or a worker pool architecture for better isolation and scalability.

The current approach of programmatically using Docker for code execution sandboxing is powerful and widely used in CI/CD, notebook environments, and agent tools. Understanding the DinD implications is essential for deploying these systems effectively.
