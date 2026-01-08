# RLM Proof of Concept

A minimal implementation of Recursive Language Models (RLMs) using FastAPI, Docker, and Claude.

## What This Does

This project demonstrates the RLM pattern: instead of chunking documents and using vector search (RAG), it loads documents into a sandboxed Python REPL and lets an LLM write code to explore them iteratively.

**Key components:**
- `rlm_session.py` - Manages Docker-based REPL sessions for document exploration
- `main.py` - FastAPI server with endpoints for uploading documents and querying them
- Documents are loaded as Python objects that Claude can programmatically navigate

## Architecture
```
User uploads JSON → Stored in ./uploads/
User queries document → Spin up Docker container with document mounted
                      → Claude generates exploration code
                      → Execute code in isolated REPL
                      → Feed results back to Claude
                      → Iterate until answer found
                      → Return synthesized answer
```

## Setup

**Prerequisites:**
- Python 3.11+
- Docker Desktop running
- Anthropic API key

**Install:**
```bash
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

**Configure:**
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

## Running

**Start the server:**
```bash
uvicorn main:app --reload
```

Server runs at `http://localhost:8000`

**Test it:**
```bash
# Upload a document
curl -X POST "http://localhost:8000/upload" \
  -F "file=@test_financial.json"

# Query it
curl -X POST "http://localhost:8000/query" \
  -F "doc_id=test_financial" \
  -F "query=What was the Q3 revenue?"

# Cleanup session
curl -X POST "http://localhost:8000/cleanup/test_financial"
```

## How It Works

### Traditional RAG
- Chunk document → Embed chunks → Store in vector DB
- Query: Embed query → Search vectors → Retrieve chunks → LLM generates answer
- **Problem:** Chunking destroys structure, semantic search isn't always what you need

### RLM Approach
- Load entire document into REPL as Python data structure
- Query: LLM writes code to explore → Execute → See results → Write more code → Repeat
- **Advantage:** Exploits document structure programmatically, iterative refinement

### Example Exploration Loop

**User asks:** "What was Q3 revenue?"

**Iteration 1:**
```python
# Claude generates:
print(type(doc))
# Output: <class 'dict'>
```

**Iteration 2:**
```python
# Claude generates:
print(doc.keys())
# Output: dict_keys(['company', 'quarters', 'employees', 'departments'])
```

**Iteration 3:**
```python
# Claude generates:
print(doc['quarters']['Q3'])
# Output: {'revenue': '$2.1M', 'expenses': '$1.2M', 'profit': '$900K'}
```

**Final answer:** "The Q3 revenue was $2.1M"

## Current State

**Working:**
- ✅ Document upload
- ✅ Docker-based REPL sessions
- ✅ Basic exploration loop with Claude
- ✅ Query endpoint returns exploration steps + final answer
- ✅ Environment variable configuration with .env
- ✅ Intelligent stopping criteria (detects currency symbols and financial data)

## POC Limitations

**This is a proof-of-concept implementation to demonstrate the RLM pattern. It is NOT production-ready.** Here's what distinguishes this POC from a production system:

### Architecture Limitations
- **In-memory storage**: Sessions stored in dictionary, lost on server restart
- **No persistence**: No database or Redis for session/document management
- **Synchronous processing**: Blocks server thread during exploration (no async workers)
- **Single-threaded**: Cannot handle concurrent queries efficiently
- **No horizontal scaling**: Cannot distribute load across multiple servers

### Functionality Gaps
- **JSON only**: No support for CSV, text, PDF, or other document formats
- **Fixed iteration limit**: Hardcoded max_iterations=5, not adaptive
- **Basic stopping logic**: Simple heuristics, not ML-based or context-aware
- **No retry/recovery**: Failed code generation or execution stops the query
- **No streaming**: Client waits for entire exploration to complete
- **No caching**: Same query on same document re-executes everything

### Security & Isolation
- **Basic Docker sandbox**: Not hardened for adversarial code execution
- **No code validation**: Generated Python code executed without static analysis
- **No authentication**: Anyone can upload/query documents
- **No authorization**: No user roles or document permissions
- **No rate limiting**: No protection against abuse or DoS
- **No resource quotas**: No per-user container limits
- **Network disabled only**: Container could be further restricted (filesystem, syscalls)

### Scalability Concerns
- **No container pooling**: Spawns new container for every document, slow startup
- **No container reuse**: Destroys container after each session cleanup
- **No load balancing**: Single server handles all requests
- **Memory leaks possible**: Active sessions not cleaned up on crashes
- **No backpressure**: Queue grows unbounded under load

### Observability & Operations
- **Console logging only**: No structured logs (JSON) for aggregation
- **No metrics**: No Prometheus/Grafana monitoring of latency, errors, costs
- **No tracing**: Cannot track request flow through system
- **No alerting**: No notifications on failures or anomalies
- **No cost tracking**: No monitoring of Anthropic API usage per query/user
- **Debug output**: Prints to console instead of proper logging framework

### Production Features Missing
- **Session persistence**: Should use Redis or PostgreSQL
- **Document preprocessing**: Should validate, normalize, and optimize documents
- **Result caching**: Should cache identical queries on same document
- **Multi-document queries**: Cannot query across multiple documents
- **Model fallback**: No retry with different model on failure
- **Prompt optimization**: Fixed system prompts, not tuned or versioned
- **Document versioning**: No tracking of document changes over time
- **Audit logging**: No record of who queried what, when
- **Cost budgets**: No per-user spending limits
- **Graceful degradation**: No fallback when Docker unavailable

### API Limitations
- **No pagination**: Returns all exploration steps regardless of size
- **No filtering**: Cannot filter which exploration steps to return
- **No versioning**: API contract can break without warning
- **No webhooks**: No async notification when query completes
- **Form encoding only**: Should support JSON request bodies
- **No batch operations**: Cannot process multiple queries at once

### Testing & Quality
- **No unit tests**: Code untested beyond manual curl commands
- **No integration tests**: Docker/API interactions not validated
- **No load tests**: Unknown behavior under concurrent load
- **No CI/CD**: No automated testing or deployment pipeline
- **No code coverage**: Don't know what's tested vs untested

**Use this POC to:**
- ✅ Understand the RLM pattern
- ✅ Experiment with document exploration strategies
- ✅ Prototype queries on structured data
- ✅ Compare RLM vs RAG approaches

**Do NOT use this POC for:**
- ❌ Production applications
- ❌ Sensitive or confidential documents
- ❌ Multi-user systems
- ❌ High-availability services
- ❌ Systems requiring audit trails

## Next Steps

**Immediate improvements:**
- [ ] Better stopping criteria (detect when answer is found)
- [ ] Support for CSV, text files, code files
- [ ] Error recovery (retry failed code generation)
- [ ] Session persistence (Redis or DB)
- [ ] Rate limiting and resource quotas

**Future enhancements:**
- [ ] Frontend UI for uploading/querying
- [ ] Multi-document queries
- [ ] Hybrid RAG + RLM (use RAG to find documents, RLM to analyze them)
- [ ] Streaming responses
- [ ] User authentication

## Why RLMs Matter

**RLMs excel at:**
- Massive structured documents (millions of tokens)
- Complex multi-hop reasoning
- Precise extraction from structured data (JSON, code, tables)
- Tasks requiring programmatic navigation

**RAG still better for:**
- Searching across document collections
- Semantic/conceptual queries
- Unstructured prose where chunking preserves meaning
- Simpler, faster retrieval

**The key insight:** Structure determines which approach wins. If document coherence comes from explicit relationships (code, schemas, cross-references), use RLMs. If it comes from semantic meaning (essays, narratives), use RAG.

## Security Notes

**Current sandbox approach:**
- Docker containers with memory limits (512MB)
- CPU quotas (50% of one core)
- Network disabled
- Document mounted read-only
- Container destroyed after use

**Production considerations:**
- Add request timeouts
- Implement rate limiting per user
- Validate generated code before execution
- Monitor container resource usage
- Implement container quotas per user

## References

- [RLM Paper](https://arxiv.org/abs/2501.00083) - Original research
- [Docker Python SDK](https://docker-py.readthedocs.io/) - Container management
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Anthropic API](https://docs.anthropic.com/) - Claude integration