# Executive Briefing — Multipurpose RAG System

**Team:** The Builders (Group1-Team6)  
**Repo:** https://github.com/capstone-2026-group1-t6/Capstone-project  
**Date:** July 2026

---

## 1. Problem

Internal teams bury answers in specs, wikis, meeting notes, and reports. Finding trustworthy information today usually means manual search or a custom pipeline for every new corpus. Small teams (5–15 people) rarely have ML infrastructure or dedicated search engineers, so knowledge stays siloed and slow to reuse.

## 2. Solution

The **Multipurpose RAG System** is an internal knowledge platform that:

1. Accepts documents (PDF, DOCX, CSV, TXT) or HuggingFace dataset URLs.
2. Automatically chunks, embeds, and indexes content for **vector**, **keyword (BM25)**, and **graph** retrieval.
3. Routes each natural-language question to the best strategy.
4. Returns a grounded answer with citations to source chunks.

No per-dataset custom engineering is required after upload.

## 3. Who it is for

| Persona | Need |
|---------|------|
| Small product / eng teams | Fast answers from their own docs |
| Ops / support | Lookup of procedures, SLOs, risks |
| Demo evaluators | One-command local stack with seed data |

**Demo corpus:** simulated company knowledge derived from [EnterpriseRAG-Bench](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench) (planning, engineering, sales, support style documents).

## 4. How it works (one screen)

```
User question
    → Strategy router (vector | hybrid | graph)
    → Retrieve top chunks (FAISS / BM25+rerank / Neo4j)
    → LLM generates answer with citations
```

| Path | Best for |
|------|----------|
| **Vector** | Semantic fact lookup |
| **Hybrid** | Cross-document / keyword-sensitive questions (vector + BM25 + cross-encoder rerank) |
| **Graph** | People, projects, reporting lines, ownership |

Full diagram: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · image: [docs/architecture.svg](docs/architecture.svg)

## 5. Key results (evaluation)

Evaluation set: **150** stratified questions (50 vector / 50 hybrid / 50 graph), 3 seeds.  
Source artifacts: `data/eval_set.jsonl`, `data/eval_results.json`.

| Criterion | Target | Result | Status |
|-----------|--------|--------|--------|
| Grounding precision | ≥ 0.75 | **0.81** (±0.03) | Pass |
| Mean latency | ≤ 5.0 s | **3.00** s (±0.18) | Pass |
| Router accuracy | ≥ 0.80 | **0.91** (±0.02) | Pass |
| Answer F1 vs gold | — | **0.84** (±0.02) | — |

**vs vector-only baseline:** grounding 0.71 → **0.81**, F1 0.73 → **0.84**.

**Error analysis:** length × source retrieval heatmap and five failure cases are in [ERROR_ANALYSIS.md](ERROR_ANALYSIS.md). Highest offline top-5 miss rates: **fireflies (62%)** and **gmail (48%)** on medium multi-chunk evidence; short confluence spans ~0% miss.

| Strategy | Grounding | F1 | Latency |
|----------|-----------|-----|---------|
| Vector | 0.76 | 0.78 | 0.98 s |
| Hybrid | 0.83 | 0.85 | 2.10 s |
| Graph | 0.86 | 0.88 | 3.92 s |

## 6. System snapshot

| Layer | Technology |
|-------|------------|
| UI | React + Vite + Nginx |
| API | FastAPI (Python 3.11) |
| Vectors | FAISS + `sentence-transformers/all-MiniLM-L6-v2` |
| Keywords | BM25 |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Graph | Neo4j 5 (88 people, ~22 projects, org relationships) |
| LLM | OpenAI-compatible client (Cerebras / Groq / Gemini) |
| Observability | Prometheus metrics |

**Ship-with-repo seed:** prebuilt corpus + indexes under `data/` so queries work after first `docker compose up --build`.

## 7. Risks and limitations

| Risk | Mitigation |
|------|------------|
| Wrong retrieval strategy | Confidence threshold; low confidence → hybrid fallback |
| Hallucinated answers | Generation constrained to retrieved context + chunk citations |
| Graph empty / unseeded | Idempotent seed on container start (`entrypoint.sh`) |
| LLM rate limits / keys | Multi-provider config (`.env.example`); graph password empty disables graph |
| Large HF ingest OOM | Streamed parquet batches; recommend Docker **6GB+** RAM |
| Synthetic / bench data | Not real PII; not production enterprise content (see [DATASET_CARD.md](DATASET_CARD.md)) |

## 8. How to run (evaluator path)

```bash
git clone https://github.com/capstone-2026-group1-t6/Capstone-project.git
cd Capstone-project
cp .env.example .env
# Set RAGPLATFORM_LLM_API_KEY (and optional base/model)
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Neo4j Browser | http://localhost:7474 (`neo4j` / `ragplatform`) |
| Prometheus | http://localhost:9090 |

Operational detail: [RUNBOOK.md](RUNBOOK.md)

## 9. Deliverables map

| Rubric item | Location |
|-------------|----------|
| Complete code | `app/`, `frontend/`, `scripts/`, Docker |
| README | [README.md](README.md) |
| Tests | `tests/` (`pytest`) |
| Executive briefing | This document |
| Architecture diagram | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/architecture.svg](docs/architecture.svg) |
| Runbook | [RUNBOOK.md](RUNBOOK.md) |
| Dataset / Model Card | [DATASET_CARD.md](DATASET_CARD.md) |
| Error analysis | [ERROR_ANALYSIS.md](ERROR_ANALYSIS.md) |
| Workflow deep-dive | [WORKFLOW.md](WORKFLOW.md) |
| Setup guide | [SETUP.md](SETUP.md) |

## 10. Team

| Name | Focus |
|------|-------|
| Nayef | Infrastructure, deployment, testing |
| Yusra | Backend / API, data acquisition |
| Eshraq | Frontend / demo UI |
| Hosam | Evaluation, monitoring, backend integration |

**Bottom line:** A small team can stand up grounded Q&A over their own documents in one Docker command — with measured retrieval quality above the project success criteria.
