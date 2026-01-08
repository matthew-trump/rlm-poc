# RLM Proof of Concept

A minimal proof-of-concept implementation of Recursive Language Models (RLMs) using FastAPI, Docker, and Claude AI. This project demonstrates an alternative to traditional RAG (Retrieval-Augmented Generation) by using LLM-generated code to explore structured documents programmatically.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-required-blue.svg)](https://www.docker.com/)

## What is RLM?

Instead of chunking documents and using vector search (RAG), RLMs load entire documents into a sandboxed Python REPL and let an LLM write code to explore them iteratively. This approach preserves document structure and enables complex multi-hop reasoning.

**Traditional RAG:**
```
Document → Chunk → Embed → Vector DB → Semantic Search → LLM Answer
```

**RLM Approach:**
```
Document → Load as Python Object → LLM Generates Exploration Code → Execute → Iterate → Answer
```

## Features

- 📄 **Document Upload** - Store JSON documents for querying
- 🐳 **Docker Sandboxing** - Isolated Python REPL environments with resource limits
- 🤖 **Claude Integration** - Uses Claude to generate exploration code
- 🔍 **Iterative Exploration** - Multi-step code generation and execution
- 📊 **Transparent Process** - Returns both final answer and exploration steps
- 🔒 **Basic Security** - Memory limits, CPU quotas, network disabled, read-only mounts

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Docker Desktop (running)
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Installation

1. **Clone the repository**
   ```bash
   git clone git@github.com:matthew-trump/rlm-poc.git
   cd rlm-poc
   ```

2. **Create virtual environment and install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your Anthropic API key
   ```

4. **Start the server**
   ```bash
   uvicorn main:app --reload
   ```

   Server runs at `http://localhost:8000`

### Usage Example

**Upload a document:**
```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@test_financial.json"
```

**Query the document:**
```bash
curl -X POST "http://localhost:8000/query" \
  -F "doc_id=test_financial" \
  -F "query=What was the Q3 revenue?"
```

**Response:**
```json
{
  "query": "What was the Q3 revenue?",
  "answer": "Based on the document data, the Q3 revenue was **$2.1M**.",
  "exploration_steps": [
    {
      "iteration": 1,
      "code": "print(type(doc))\nprint(doc.keys())",
      "output": "<class 'dict'>\ndict_keys(['company', 'quarters', 'employees', 'departments'])"
    },
    {
      "iteration": 2,
      "code": "print(doc['quarters']['Q3'])",
      "output": "{'revenue': '$2.1M', 'expenses': '$1.2M', 'profit': '$900K'}"
    }
  ],
  "iterations_used": 2
}
```

**Cleanup session:**
```bash
curl -X POST "http://localhost:8000/cleanup/test_financial"
```

## How It Works

1. **Upload**: Store JSON document in `./uploads/` directory
2. **Query**: User submits natural language query
3. **Container Spin-up**: Docker container created with document mounted read-only
4. **Exploration Loop**:
   - Claude generates Python code to explore the document
   - Code executes in isolated container
   - Results fed back to Claude
   - Process repeats until answer found (max 5 iterations)
5. **Answer**: Claude synthesizes final answer from exploration results
6. **Cleanup**: Container destroyed when session ends

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────┐
│      FastAPI Server             │
│  ┌──────────────────────────┐   │
│  │   main.py                │   │
│  │  - /upload               │   │
│  │  - /query                │   │
│  │  - /cleanup              │   │
│  └──────────┬───────────────┘   │
└─────────────┼───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│   REPLSession (rlm_session.py)  │
│  ┌──────────────────────────┐   │
│  │  Docker Container        │   │
│  │  - Python 3.11           │   │
│  │  - Document mounted      │   │
│  │  - Network disabled      │   │
│  │  - Resource limits       │   │
│  └──────────────────────────┘   │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│     Claude API                  │
│  - Code generation              │
│  - Answer formulation           │
└─────────────────────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information |
| `/upload` | POST | Upload JSON document |
| `/query` | POST | Query document with natural language |
| `/cleanup/{doc_id}` | POST | Clean up session for document |

## Example Queries

The included `test_financial.json` supports queries like:

- "What was the Q3 revenue?"
- "What was the total profit across all quarters?"
- "Which quarter had the highest revenue?"
- "How many employees does the company have?"
- "What departments exist in the company?"

## When to Use RLMs vs RAG

**RLMs Excel At:**
- ✅ Structured documents (JSON, code, tables)
- ✅ Complex multi-hop reasoning
- ✅ Precise data extraction
- ✅ Documents with explicit relationships

**RAG Better For:**
- ✅ Unstructured prose (essays, articles)
- ✅ Semantic/conceptual queries
- ✅ Large document collections
- ✅ Fast retrieval requirements

**Key Insight:** Document structure determines the best approach. Use RLMs for structured data with programmatic relationships, RAG for semantic meaning in prose.

## ⚠️ Important: This is a POC

**This is a proof-of-concept to demonstrate the RLM pattern. It is NOT production-ready.**

Key limitations:
- No authentication or authorization
- In-memory session storage (lost on restart)
- JSON documents only
- Basic security sandbox
- No horizontal scaling
- No monitoring or observability
- Synchronous processing only

See [CLAUDE.md](./CLAUDE.md) for detailed POC limitations and production requirements.

**Use for:** Learning, experimentation, prototyping

**Do NOT use for:** Production apps, sensitive data, multi-user systems

## Project Structure

```
rlm-poc/
├── main.py              # FastAPI server and endpoints
├── rlm_session.py       # Docker REPL session management
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── test_financial.json  # Sample document
├── uploads/             # Uploaded documents (gitignored)
├── CLAUDE.md            # Detailed documentation
└── README.md            # This file
```

## Documentation

- **[CLAUDE.md](./CLAUDE.md)** - Detailed implementation guide, POC limitations, and future roadmap
- **[RLM Paper](https://arxiv.org/abs/2501.00083)** - Original research on Recursive Language Models
- **[FastAPI Docs](https://fastapi.tiangolo.com/)** - Web framework documentation
- **[Anthropic API](https://docs.anthropic.com/)** - Claude integration guide

## Development

**Run tests:**
```bash
# TODO: Add test suite
```

**Code structure:**
- `REPLSession` - Manages Docker container lifecycle
- `SimpleRLM` - Handles Claude API interaction
- FastAPI routes - HTTP endpoints for upload/query/cleanup

## Contributing

This is a proof-of-concept project. Contributions welcome for:
- Additional document format support (CSV, PDF, text)
- Improved stopping criteria
- Error recovery and retry logic
- Test suite
- Frontend UI

## License

MIT License - See LICENSE file for details

## References

- [Recursive Language Models Paper](https://arxiv.org/abs/2501.00083)
- [Docker Python SDK](https://docker-py.readthedocs.io/)
- [FastAPI Framework](https://fastapi.tiangolo.com/)
- [Anthropic Claude API](https://docs.anthropic.com/)

## Questions?

For detailed implementation notes and architectural decisions, see [CLAUDE.md](./CLAUDE.md).

---

Built with ❤️ to explore the RLM pattern
