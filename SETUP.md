# RAG Platform — Setup Guide

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Docker Desktop | 4.x+ | Runs all services (Neo4j, API, Frontend, Prometheus) |
| Docker Compose | v2.x+ | Multi-container orchestration |
| Git | Latest | Clone the repository |
| Groq API Key | — | LLM for answer generation and graph queries |
| RAM | 6GB+ allocated to Docker | Neo4j + API + embedding models in memory |

## Quick Start (One Command)

```bash
git clone <repo-url>
cd capstone-project
cp .env.example .env
# Edit .env — add your Groq API key
docker compose up --build
```

This starts all 4 services and auto-seeds Neo4j with 88 people and 24 projects.

## Step-by-Step Setup

### 1. Clone and Configure

```bash
git clone <repo-url>
cd capstone-project
cp .env.example .env
```

Edit `.env` and set your API key:

```
RAGPLATFORM_LLM_API_KEY=gsk_your_groq_api_key_here
```

Get a free key at https://console.groq.com.

### 2. Build and Start

```bash
docker compose up --build
```

First run takes ~5 minutes (pulls base images, installs Python/Node deps, builds frontend).

### 3. Wait for Health

Watch the logs. You'll see:

```
rag-platform-api  | ==> Seeding Neo4j graph...
rag-platform-api  | Seeded 88 people and 22 projects into Neo4j.
rag-platform-api  | ==> Starting API server...
rag-platform-api  | INFO:     Uvicorn running on http://0.0.0.0:8000
rag-platform-api  | INFO:     Application startup complete.
```

### 4. Open the UI

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **API Docs** | http://localhost:8000/docs |
| **Neo4j Browser** | http://localhost:7474 (login: `neo4j` / `ragplatform`) |
| **Prometheus** | http://localhost:9090 |

## Services

| Service | Port | Description |
|---------|------|-------------|
| `neo4j` | 7474, 7687 | Graph database — auto-seeded with org data |
| `api` | 8000 | FastAPI backend — ingest, query, health, metrics |
| `frontend` | 5173 | React/Vite UI |
| `prometheus` | 9090 | Metrics collection |

## What Happens on Startup

```
docker compose up --build
        │
        ▼
┌─────────────────────────────────────────┐
│  1. Neo4j starts, healthcheck waits     │
│     for bolt port (7687)                │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  2. API container runs entrypoint.sh:   │
│     a. build_graph_index.py seeds       │
│        Neo4j (88 people, 24 projects,   │
│        89 relationships)                │
│     b. uvicorn starts FastAPI server    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  3. FastAPI startup loads:              │
│     a. FAISS index (corpus.faiss)       │
│     b. BM25 index (corpus_bm25.pkl)     │
│     c. Neo4j connection                 │
│     d. Embedding models (all-MiniLM)    │
│     e. Reranker (ms-marco-MiniLM)      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  4. Frontend (Nginx) starts once API    │
│     is healthy                          │
└─────────────────────────────────────────┘
```

## First-Time Data Ingest

The corpus is pre-built (1,500 chunks from EnterpriseRAG-Bench). If you need to re-ingest or add new data:

### Ingest via UI

1. Go to http://localhost:5173
2. Upload files (PDF, DOCX, CSV, TXT) or paste a HuggingFace dataset URL
3. Files are chunked, embedded, and indexed automatically

### Ingest via API

```bash
# Upload a file
curl -X POST http://localhost:8000/ingest/upload \
  -F "files=@document.pdf"

# Ingest a HuggingFace dataset (background job)
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://huggingface.co/datasets/user/dataset"}'

# Check background job status
curl http://localhost:8000/ingest/jobs/{job_id}
```

### Query via API

```bash
# Hybrid search (default)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the onboarding risks?", "top_k": 5}'

# Force graph search
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who reports to Sean Gallagher?", "forced_strategy": "graph"}'
```

## Docker Desktop Settings

For HuggingFace dataset ingest, increase Docker memory:

- **Docker Desktop → Settings → Resources → Memory**: set to **6GB+**
- HuggingFace streaming buffers parquet data —低于 6GB may OOM

## Common Commands

```bash
# Start (background mode)
docker compose up -d

# Start with fresh build
docker compose up --build

# Stop all services
docker compose down

# Stop and remove volumes (fresh start)
docker compose down -v

# View API logs
docker compose logs -f api

# View Neo4j logs
docker compose logs -f neo4j

# Rebuild only the API
docker compose build api && docker compose up -d api

# Shell into API container
docker compose exec api bash

# Shell into Neo4j
docker compose exec neo4j cypher-shell -u neo4j -p ragplatform
```

## Troubleshooting

### API won't start / crash loop

```bash
docker compose logs api | tail -20
```

Common causes:
- Missing `.env` file — copy from `.env.example`
- Invalid Groq API key
- Docker memory < 6GB

### Neo4j connection refused

API waits for Neo4j healthcheck. If it fails:
```bash
docker compose restart neo4j
sleep 30
docker compose restart api
```

### Frontend shows blank page

```bash
docker compose build frontend && docker compose up -d frontend
```

### Graph queries return "No relevant context"

Neo4j may not be seeded. Check:
```bash
docker compose exec neo4j cypher-shell -u neo4j -p ragplatform \
  "MATCH (n) RETURN labels(n), count(n)"
```

If empty, re-seed:
```bash
docker compose exec api python scripts/build_graph_index.py
```

### Index not found warnings

If you see "No corpus index found" in logs, rebuild:
```bash
docker compose exec api python scripts/build_corpus_index.py
```

## Reliability — How to Ensure a Good Run Every Time

### Before Starting

1. Docker Desktop open, **6GB+ memory** allocated
2. `.env` has your Groq API key set
3. `data/seed/corpus.jsonl` has chunks (pre-built, ships with repo)
4. `data/index/corpus.faiss` exists (pre-built, ships with repo)

### Start and Verify

```bash
docker compose up --build
```

Wait ~45s for startup, then verify:

```bash
curl http://localhost:8000/health
# → {"status": "ok"}

curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "top_k": 1}'
# → should return an answer, not an error
```

### If Something Breaks — Full Reset

```bash
docker compose down -v
docker compose up --build
```

This wipes Neo4j volume, rebuilds all containers, re-seeds graph, re-loads indexes. Takes ~2 minutes. Fresh start every time.

### Rules to Prevent Breakage

1. **Never delete `data/`** — it has your corpus and indexes. Without it, queries return nothing.
2. **Don't change `.env` after first setup** — especially the Groq API key. Wrong key = no LLM answers.
3. **Keep Docker memory at 6GB+** — HF dataset ingest and embedding models need it.
4. **Don't run multiple instances** — stop one before starting another (`docker compose down`).
5. **If you pull new code and it breaks**, run:
   ```bash
   docker compose down -v
   docker compose up --build
   ```
6. **If you just want to restart safely** (no data loss):
   ```bash
   docker compose restart api
   ```
7. **Before closing your laptop / shutting down**, run `docker compose down` to save Neo4j state cleanly.

### Self-Healing

The system recovers automatically on every start:
- `entrypoint.sh` re-seeds Neo4j (idempotent MERGE)
- API reloads FAISS + BM25 indexes from disk
- You can always recover with `docker compose down -v && docker compose up --build`

## Project Structure

```
capstone-project/
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic settings from env vars
│   │   ├── state.py           # Global singleton (indexes, services)
│   │   └── schemas.py         # Pydantic models
│   ├── routers/
│   │   ├── ingest.py          # POST /ingest/upload, /url, GET /jobs
│   │   ├── query.py           # POST /query — main entry point
│   │   └── health.py          # GET /health
│   ├── services/
│   │   ├── ingest_service.py  # File/URL parsing, chunking, indexing
│   │   ├── corpus_index.py    # FAISS + BM25 build/save/load
│   │   ├── router_service.py  # Strategy selection (vector/hybrid/graph)
│   │   ├── vector_service.py  # FAISS cosine search
│   │   ├── hybrid_service.py  # Vector + BM25 + reranker
│   │   ├── graph_service.py   # NL→Cypher + Neo4j
│   │   ├── generate_service.py # LLM answer generation
│   │   ├── llm_client.py      # Groq API wrapper
│   │   ├── graph_driver.py    # Neo4j async driver
│   │   ├── nl_to_cypher.py    # Natural language to Cypher
│   │   ├── query_classifier.py # Rule-based strategy router
│   │   └── reranker.py        # Cross-encoder reranker
│   └── main.py                # FastAPI app, lifespan, middleware
├── frontend/
│   ├── src/
│   │   ├── pages/upload.jsx   # Upload + HuggingFace ingest
│   │   ├── pages/query.jsx    # Query interface
│   │   └── lib/api.js         # API client
│   ├── Dockerfile             # Multi-stage build (Node → Nginx)
│   └── nginx.conf
├── scripts/
│   ├── build_graph_index.py   # Seeds Neo4j from graph_seed.json
│   ├── build_corpus_index.py  # Builds FAISS + BM25 from corpus.jsonl
│   └── fetch_seed_data.py     # Downloads seed corpus
├── data/
│   ├── seed/
│   │   ├── corpus.jsonl       # Chunk storage (source of truth)
│   │   └── graph_seed.json    # Neo4j seed data
│   ├── index/
│   │   ├── corpus.faiss       # FAISS vector index
│   │   ├── corpus_meta.jsonl  # Chunk metadata
│   │   └── corpus_bm25.pkl    # BM25 keyword index
│   └── uploads/               # Uploaded file chunks
├── monitoring/
│   └── prometheus.yml         # Prometheus scrape config
├── docker-compose.yml         # 4-service orchestration
├── Dockerfile                 # API container (Python 3.11)
├── entrypoint.sh              # Seeds Neo4j, starts uvicorn
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
└── WORKFLOW.md                # Architecture documentation
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RAGPLATFORM_ENVIRONMENT` | `local` | Environment name |
| `RAGPLATFORM_LLM_API_KEY` | — | Groq API key (required) |
| `RAGPLATFORM_LLM_API_BASE` | — | Custom LLM endpoint (optional) |
| `RAGPLATFORM_ROUTER_CONFIDENCE_THRESHOLD` | `0.75` | Below this, falls back to hybrid |
| `RAGPLATFORM_DEFAULT_TOP_K` | `5` | Default chunks returned per query |
| `RAGPLATFORM_GRAPH_DB_URI` | `bolt://localhost:7687` | Neo4j bolt URI |
| `RAGPLATFORM_GRAPH_DB_USER` | `neo4j` | Neo4j username |
| `RAGPLATFORM_GRAPH_DB_PASSWORD` | — | Neo4j password (empty = disable graph) |
| `RAGPLATFORM_GRAPH_DB_DATABASE` | `neo4j` | Neo4j database name |
