# RAG Platform — Workflow Documentation

## Architecture Overview

```
┌─────────────┐     ┌──────────┐     ┌─────────────────────────────────┐
│   Frontend   │────▶│   API    │────▶│  Ingest or Query                │
│  React/Vite  │◀────│ FastAPI  │◀────│                                 │
└─────────────┘     └──────────┘     │  Ingest:                        │
                                      │   chunk → corpus.jsonl          │
                                      │   embed → FAISS index           │
                                      │   rebuild → BM25 index          │
                                      │   extract → Neo4j (optional)    │
                                      │                                 │
                                      │  Query:                         │
                                      │   router → vector/hybrid/graph  │
                                      │   retrieve → chunks             │
                                      │   generate → LLM answer         │
                                      └─────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼────────────────────────┐
                    ▼                         ▼                        ▼
             ┌─────────────┐          ┌──────────────┐         ┌──────────┐
             │ FAISS Index  │          │ BM25 Index   │         │  Neo4j   │
             │ (vectors)    │          │ (keywords)   │         │ (graph)  │
             └─────────────┘          └──────────────┘         └──────────┘
```

## Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| `neo4j` | 7474 (browser), 7687 (bolt) | Graph database for structured relationships |
| `api` | 8000 | FastAPI backend (ingest, query, health, metrics) |
| `frontend` | 5173 | React/Vite UI |
| `prometheus` | 9090 | Metrics collection |

## Startup Sequence

```bash
docker compose up --build
```

1. **Neo4j** starts first. Healthcheck waits for bolt port to be ready.
2. **API container** runs `entrypoint.sh`:
   - `scripts/build_graph_index.py` seeds Neo4j with 88 people, 24 projects, 89 relationships (idempotent MERGE).
   - `uvicorn` starts, triggering `query.py` module-level initialization:
     - Loads FAISS index from `data/index/corpus.faiss`
     - Loads BM25 index from `data/index/corpus_bm25.pkl`
     - Connects to Neo4j
     - Creates `IngestService`, `VectorService`, `HybridService`, `GraphService`, `GenerateService`, `RouterService`
3. **Frontend** (Vite/React) serves on `:5173` once API is healthy.

---

## Ingest Flow

### File Upload — `POST /ingest/upload`

```
Frontend → POST /ingest/upload (multipart/form-data)
         → ingest_service.ingest_file()
```

1. Parse file (PDF, DOCX, CSV, or plain text).
2. `_chunk_text()` splits into ~1500 character chunks with 200 character overlap.
3. Append chunks to `data/seed/corpus.jsonl`.
4. `corpus_index.add_chunks()` — embeds with SentenceTransformer (`all-MiniLM-L6-v2`), adds to FAISS, saves to disk.
5. `keyword_index.rebuild()` — rebuilds BM25 from full corpus, saves to disk.
6. If LLM + Neo4j are configured: extract graph entities via LLM, write to Neo4j.
7. Update `data/uploads/manifest.jsonl`.
8. Return `{doc_id, status: "indexed", chunk_count}`.

### HuggingFace Dataset — `POST /ingest/url`

```
Frontend → POST /ingest/url {url: "https://huggingface.co/datasets/..."}
         → ingest_service.ingest_url()
         → Returns {job_id, status: "processing"} immediately
         → asyncio.create_task(_process_hf_dataset_background())
```

Background worker:

1. Stream-download parquet via httpx (no full-file buffer in memory — avoids OOM).
2. Read with `pyarrow.ParquetFile.iter_batches(batch_size=200)`.
3. For each row: `_chunk_text()` → append to `all_chunks` (cap: 1500 total, 200 per source type).
4. Append all chunks to `data/seed/corpus.jsonl`.
5. `corpus_index.add_chunks()` + `keyword_index.rebuild()` — hot-swap indexes into live services.
6. Frontend polls `GET /ingest/jobs/{job_id}` until `status: "completed"`.

### Regular URL — `POST /ingest/url` (non-HuggingFace)

1. Streaming download via httpx (50MB cap, 60s timeout).
2. HTML parsing with BeautifulSoup.
3. Chunk, index, and manifest update (same as file upload flow).

---

## Query Flow — `POST /query`

```
Frontend → POST /query {query: "...", top_k: 5}
         → router_service.route(query)
```

### Step 1 — Strategy Router (`router_service.py`)

- `RuleBasedClassifier.predict(query)` → returns `("vector" | "hybrid" | "graph", confidence)`.
- If confidence < threshold (0.6) → **falls back to hybrid** (Risk 1 mitigation).
- Can be overridden: `{query: "...", forced_strategy: "graph"}`.

### Step 2 — Retrieval

| Strategy | What it does |
|----------|-------------|
| **Vector** | FAISS cosine similarity search → top-k chunks |
| **Hybrid** | FAISS search (2×k) + BM25 search (2×k) → merge by score → cross-encoder rerank → top-k |
| **Graph** | NL→Cypher translation via LLM → Neo4j query → returns person/project/relationship chunks |

#### Vector Search (`vector_service.py`)

- Encodes query with SentenceTransformer.
- FAISS nearest-neighbor search.
- Returns `RetrievedChunk` objects with cosine similarity scores.

#### Hybrid Search (`hybrid_service.py`)

- Runs vector search (2×k) and BM25 keyword search (2×k) in parallel.
- Merges results by chunk_id, keeping the higher score for duplicates.
- Sorts by score descending.
- Cross-encoder reranker (`ms-marco-MiniLM-L6-v2`) re-scores top candidates.
- Returns top-k after reranking.

#### Graph Search (`graph_service.py`)

- `NLToCypher.translate(query)` uses LLM to convert natural language to Cypher.
- Executes Cypher against Neo4j.
- Returns `RetrievedChunk` objects with relationship context.

### Step 3 — Generation (`generate_service.py`)

- Builds context from retrieved chunks: `[{chunk_id}] {text}\n\n...`
- Calls LLM (Groq) with query + context + conversation history.
- Returns `{answer, citations: [chunk_ids], strategy_used, latency}`.

---

## Neo4j Graph Schema

### Node Types

| Label | Count | Properties |
|-------|-------|------------|
| `Person` | 88 | `name`, `title` |
| `Project` | 24 | `name` |

### Relationship Types

| Type | Count | From → To |
|------|-------|-----------|
| `REPORTS_TO` | 18 | Person → Person |
| `WORKS_ON` | 16 | Person → Project |
| `OWNS` | 7 | Person → Project |
| `COLLABORATES_WITH` | 48 | Person → Person |

### Seeding

- Auto-seeded on `docker compose up --build` via `entrypoint.sh` → `scripts/build_graph_index.py`.
- Reads `data/seed/graph_seed.json` (88 people extracted from EnterpriseRAG-Bench corpus).
- Idempotent MERGE — safe to re-run.

---

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, lifespan, CORS, Prometheus instrumentation |
| `app/routers/ingest.py` | `POST /ingest/upload`, `POST /ingest/url`, `GET /ingest/jobs/{id}` |
| `app/routers/query.py` | `POST /query` — loads indexes, wires services, serves queries |
| `app/services/ingest_service.py` | File/URL parsing, chunking, index rebuild, Neo4j write |
| `app/services/corpus_index.py` | `CorpusIndex` (FAISS) and `KeywordIndex` (BM25) build/save/load/search |
| `app/services/router_service.py` | Strategy selection (vector/hybrid/graph) with confidence threshold |
| `app/services/vector_service.py` | FAISS cosine similarity search |
| `app/services/hybrid_service.py` | Vector + BM25 merge + cross-encoder rerank |
| `app/services/graph_service.py` | NL→Cypher + Neo4j query execution |
| `app/services/generate_service.py` | LLM grounded answer generation with citations |
| `app/services/graph_driver.py` | Async Neo4j driver wrapper |
| `app/services/nl_to_cypher.py` | Natural language to Cypher translation via LLM |
| `app/core/state.py` | Global singleton state (indexes, services, job registry) |
| `app/core/config.py` | Pydantic settings from env vars |
| `entrypoint.sh` | Docker entrypoint — seeds Neo4j, then starts uvicorn |
| `scripts/build_graph_index.py` | Neo4j seed script (graph_seed.json → Neo4j) |
| `scripts/build_corpus_index.py` | Standalone FAISS + BM25 index builder |
| `data/seed/corpus.jsonl` | Chunk storage (appended by ingest) |
| `data/seed/graph_seed.json` | Neo4j seed data (88 people, 24 projects) |
| `data/index/corpus.faiss` | FAISS vector index |
| `data/index/corpus_meta.jsonl` | Chunk metadata |
| `data/index/corpus_bm25.pkl` | BM25 keyword index |
| `data/uploads/manifest.jsonl` | Upload manifest |

---

## Data Flow Diagram

```
                    ┌──────────────────────────────────────────┐
                    │              INGEST PATH                 │
                    └──────────────────────────────────────────┘

  File Upload / URL                HuggingFace Dataset
        │                                │
        ▼                                ▼
  ┌───────────┐                ┌─────────────────────┐
  │  Parse     │                │  Stream parquet via  │
  │  (PDF/DOCX │                │  httpx, read with    │
  │   /CSV/TXT)│                │  pyarrow batches     │
  └─────┬─────┘                └──────────┬──────────┘
        │                                 │
        ▼                                 ▼
  ┌─────────────────────────────────────────────┐
  │         _chunk_text()                       │
  │   ~1500 char chunks, 200 char overlap       │
  └──────────────────┬──────────────────────────┘
                     │
        ┌────────────┼────────────────┐
        ▼            ▼                ▼
  ┌──────────┐ ┌──────────┐    ┌──────────┐
  │ corpus   │ │  FAISS   │    │  BM25    │
  │ .jsonl   │ │  index   │    │  index   │
  └──────────┘ └──────────┘    └──────────┘
        │
        ▼ (optional)
  ┌──────────┐
  │  Neo4j   │
  │  (LLM    │
  │  extract)│
  └──────────┘


                    ┌──────────────────────────────────────────┐
                    │               QUERY PATH                 │
                    └──────────────────────────────────────────┘

                    ┌─────────────────┐
                    │  User Query     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Router Service │
                    │  (classify)     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Vector  │  │  Hybrid  │  │  Graph   │
        │  FAISS   │  │ FAISS +  │  │ NL→Cypher│
        │  search  │  │ BM25 +   │  │ + Neo4j  │
        │          │  │ reranker │  │          │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Generate       │
                   │  (LLM + context │
                   │   + citations)  │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Response:      │
                   │  answer,        │
                   │  citations,     │
                   │  strategy_used, │
                   │  latency        │
                   └─────────────────┘
```
