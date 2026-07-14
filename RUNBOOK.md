# Runbook — Multipurpose RAG System

Operational guide for deploy, verify, troubleshoot, and recover.  
Companion setup narrative: [SETUP.md](SETUP.md). Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 1. Service map

| Service | Container | Ports | Role |
|---------|-----------|-------|------|
| Neo4j | `rag-platform-neo4j` | 7474 (UI), 7687 (Bolt) | Graph store |
| API | `rag-platform-api` | 8000 | Ingest, query, health, metrics |
| Frontend | `rag-platform-frontend` | 5173 → 80 | React UI (Nginx) |
| Prometheus | `rag-platform-prometheus` | 9090 | Metrics scrape |

**Auth defaults (local Docker):** Neo4j user `neo4j` / password `ragplatform`.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|--------|
| Docker Desktop 4.x+ / Compose v2 | Full stack |
| **6GB+ RAM** allocated to Docker | Embeddings + Neo4j + HF ingest |
| LLM API key | OpenAI-compatible (Cerebras recommended; Groq/Gemini also work) |
| Git | Clone repo |

---

## 3. Deploy (happy path)

```bash
git clone https://github.com/capstone-2026-group1-t6/Capstone-project.git
cd Capstone-project
cp .env.example .env
```

Edit `.env` — minimum:

```env
RAGPLATFORM_LLM_API_KEY=your_key_here
# Recommended for eval throughput:
RAGPLATFORM_LLM_API_BASE=https://api.cerebras.ai/v1
RAGPLATFORM_LLM_MODEL=gpt-oss-120b
```

Start:

```bash
docker compose up --build
```

First build ≈ 5 minutes. On API start, `entrypoint.sh`:

1. Seeds Neo4j from `data/seed/graph_seed.json` (idempotent MERGE).
2. Starts Uvicorn; loads FAISS + BM25 from `data/index/`.

Detach mode:

```bash
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

---

## 4. Health checks

| Check | Command / URL | Expect |
|-------|----------------|--------|
| API health | `curl http://localhost:8000/health` | `{"status":"ok"}` (or equivalent OK) |
| API docs | http://localhost:8000/docs | Swagger UI |
| Frontend | http://localhost:5173 | Home + Chat + Upload |
| Neo4j | http://localhost:7474 | Browser login works |
| Prometheus | http://localhost:9090 | Targets UI |
| Smoke query | See below | Answer JSON, not 5xx |

Smoke query:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"What are the top risks for the Northstar on-prem deployment?\", \"top_k\": 3}"
```

Graph force:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"Who reports to Sean Gallagher?\", \"forced_strategy\": \"graph\"}"
```

Neo4j node counts:

```bash
docker compose exec neo4j cypher-shell -u neo4j -p ragplatform \
  "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC"
```

---

## 5. Routine operations

### Logs

```bash
docker compose logs -f api
docker compose logs -f neo4j
docker compose logs -f frontend
```

### Restart without data wipe

```bash
docker compose restart api
```

### Rebuild API only

```bash
docker compose build api
docker compose up -d api
```

### Ingest (UI)

1. Open http://localhost:5173 → Upload  
2. PDF / DOCX / CSV / TXT, or HuggingFace dataset URL  
3. Wait for job completion; query from Chat

### Ingest (API)

```bash
curl -X POST http://localhost:8000/ingest/upload -F "files=@document.pdf"

curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://huggingface.co/datasets/user/dataset\"}"

curl http://localhost:8000/ingest/jobs/{job_id}
```

### Rebuild indexes (inside API container)

```bash
docker compose exec api python scripts/build_corpus_index.py
docker compose exec api python scripts/build_graph_index.py
```

### Unit tests (host, with venv)

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

### Evaluation harness

```bash
# Stack must be up and healthy
python scripts/run_eval.py
# Results: data/eval_results.json
```

---

## 6. Environment variables

| Variable | Default / note | Purpose |
|----------|----------------|---------|
| `RAGPLATFORM_LLM_API_KEY` | **required** | LLM auth |
| `RAGPLATFORM_LLM_API_BASE` | empty → Groq default in client | Provider base URL |
| `RAGPLATFORM_LLM_MODEL` | provider-dependent | Chat model id |
| `RAGPLATFORM_ROUTER_CONFIDENCE_THRESHOLD` | `0.6` | Below → hybrid fallback |
| `RAGPLATFORM_DEFAULT_TOP_K` | `5` | Chunks per query |
| `RAGPLATFORM_MAX_QUERY_LATENCY_SECONDS` | `5.0` | Latency budget (config) |
| `RAGPLATFORM_GRAPH_DB_URI` | Compose sets `bolt://neo4j:7687` | Neo4j |
| `RAGPLATFORM_GRAPH_DB_USER` | `neo4j` | Neo4j user |
| `RAGPLATFORM_GRAPH_DB_PASSWORD` | Compose: `ragplatform`; empty disables graph | Neo4j password |
| `RAGPLATFORM_GRAPH_DB_DATABASE` | `neo4j` | DB name |

Full template: `.env.example`.

---

## 7. Incident playbook

### 7.1 API crash loop / won't start

```bash
docker compose logs api --tail 50
```

| Symptom | Action |
|---------|--------|
| Missing env / key errors | `cp .env.example .env` and set `RAGPLATFORM_LLM_API_KEY` |
| OOM / killed | Docker Desktop → Resources → Memory **≥ 6GB** |
| Neo4j not ready | Wait for Neo4j healthy; `docker compose restart api` |

### 7.2 Neo4j connection refused

```bash
docker compose restart neo4j
# wait ~30s
docker compose restart api
```

### 7.3 Graph answers empty / “No relevant context”

```bash
docker compose exec api python scripts/build_graph_index.py
```

Verify seed file exists: `data/seed/graph_seed.json`.

### 7.4 “No corpus index” / empty retrieval

```bash
docker compose exec api python scripts/build_corpus_index.py
```

Do **not** delete `data/` — it holds corpus and indexes.

### 7.5 Frontend blank page

```bash
docker compose build frontend
docker compose up -d frontend
```

Confirm API health first (`:8000/health`).

### 7.6 LLM errors / rate limits

- Switch provider in `.env` (Cerebras / Groq / Gemini) per `.env.example`.  
- Restart API after env change: `docker compose up -d api`.

### 7.7 Full reset (destructive)

Wipes Neo4j volume; rebuilds containers; re-seeds graph; reloads disk indexes.

```bash
docker compose down -v
docker compose up --build
```

---

## 8. Data you must not delete

| Path | Contents |
|------|----------|
| `data/seed/corpus.jsonl` | Chunk store |
| `data/seed/graph_seed.json` | Graph seed |
| `data/index/corpus.faiss` | Vector index |
| `data/index/corpus_meta.jsonl` | Vector metadata |
| `data/index/corpus_bm25.pkl` | BM25 index |
| `data/uploads/` | Upload manifests / chunk side-cars |

---

## 9. Self-healing on every start

1. `entrypoint.sh` re-seeds Neo4j (MERGE — safe to re-run).  
2. API reloads FAISS + BM25 from disk.  
3. If state is corrupt: `docker compose down -v && docker compose up --build`.

---

## 10. Contacts / ownership

| Area | Owner (team contract) |
|------|------------------------|
| Infra / deploy / tests | Nayef |
| Backend / data | Yusra |
| Frontend | Eshraq |
| Eval / monitoring/backend | Hosam |

Repo: https://github.com/capstone-2026-group1-t6/Capstone-project  
Team contract: [TEAM_CONTRACT.md](TEAM_CONTRACT.md)
