# Architecture — Multipurpose RAG System

Visual diagram: **[architecture.png](architecture.png)** · **[architecture.svg](architecture.svg)** (also embedded below).

---

## System context

```mermaid
flowchart LR
  User([User / Evaluator])
  UI[React Frontend<br/>:5173]
  API[FastAPI<br/>:8000]
  Prom[Prometheus<br/>:9090]
  FAISS[(FAISS)]
  BM25[(BM25)]
  Neo4j[(Neo4j)]
  LLM[External LLM API]

  User --> UI --> API
  API --> FAISS
  API --> BM25
  API --> Neo4j
  API --> LLM
  Prom -->|scrape metrics| API
```

---

## Query path

```mermaid
sequenceDiagram
  participant U as User
  participant F as Frontend
  participant A as API /query
  participant R as Router
  participant V as Vector / Hybrid / Graph
  participant L as LLM

  U->>F: Ask question
  F->>A: POST /query
  A->>R: classify strategy
  R-->>A: vector | hybrid | graph
  A->>V: retrieve top-k chunks
  V-->>A: chunks + scores
  A->>L: generate grounded answer
  L-->>A: text
  A-->>F: answer + citations + strategy + latency
  F-->>U: Chat UI
```

---

## Ingest path

```mermaid
flowchart TD
  A[Upload file / HF URL / web URL] --> B[Parse & chunk<br/>~1500 chars, 200 overlap]
  B --> C[Append corpus.jsonl]
  B --> D[Embed all-MiniLM-L6-v2]
  D --> E[Update FAISS]
  C --> F[Rebuild BM25]
  B --> G{LLM + Neo4j?}
  G -->|yes| H[Entity extract → Neo4j]
  G -->|no| I[Skip graph write]
  E --> J[Hot-swap indexes in memory]
  F --> J
```

---

## Component map

| Component | Responsibility |
|-----------|----------------|
| `frontend/` | Home, Upload, Chat UI |
| `app/routers/ingest.py` | File/URL ingest + jobs |
| `app/routers/query.py` | Query orchestration, service wiring |
| `app/routers/health.py` | Liveness |
| `app/services/router_service.py` | Strategy selection + confidence fallback |
| `app/services/vector_service.py` | FAISS search |
| `app/services/hybrid_service.py` | Vector + BM25 merge + rerank |
| `app/services/graph_service.py` | NL→Cypher + Neo4j |
| `app/services/generate_service.py` | Grounded generation |
| `app/services/ingest_service.py` | Parse, chunk, index, optional graph extract |
| `data/seed/` + `data/index/` | Durable corpus and indexes |
| `monitoring/prometheus.yml` | Scrape config |

Deep narrative: [../WORKFLOW.md](../WORKFLOW.md). Ops: [../RUNBOOK.md](../RUNBOOK.md).

---

## Diagram

![Architecture diagram](architecture.png)
