# Multipurpose RAG System

**Team:** The Builders (Group1-Team6)  
**Repo:** https://github.com/capstone-2026-group1-t6/Capstone-project

Internal knowledge Q&A: upload documents (or a HuggingFace dataset), ask natural-language questions, and get **grounded answers with citations**. The API routes each query to **vector**, **hybrid** (vector + BM25 + rerank), or **graph** (Neo4j / NL→Cypher) retrieval.

---

## Final submission deliverables

| Rubric item | Location |
|-------------|----------|
| **Executive briefing** | [EXECUTIVE_BRIEFING.md](EXECUTIVE_BRIEFING.md) |
| **Architecture diagram** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/architecture.svg](docs/architecture.svg) |
| **Runbook** | [RUNBOOK.md](RUNBOOK.md) |
| **Dataset / Model Card** | [DATASET_CARD.md](DATASET_CARD.md) |
| **Error analysis** | [ERROR_ANALYSIS.md](ERROR_ANALYSIS.md) (length × source heatmap + 5 failure cases) |
| **Tests** | [`tests/`](tests/) — run with `pytest -v` |
| **Code** | [`app/`](app/), [`frontend/`](frontend/), [`scripts/`](scripts/), Docker |
| Setup guide (extended) | [SETUP.md](SETUP.md) |
| Workflow deep-dive | [WORKFLOW.md](WORKFLOW.md) |
| Team contract | [TEAM_CONTRACT.md](TEAM_CONTRACT.md) |
| Sample queries | [TEST_QUERIES.md](TEST_QUERIES.md) |

---

## Quick start

```bash
git clone https://github.com/capstone-2026-group1-t6/Capstone-project.git
cd Capstone-project
cp .env.example .env
# Set RAGPLATFORM_LLM_API_KEY (see .env.example for Cerebras / Groq / Gemini)
docker compose up --build
```

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **API docs** | http://localhost:8000/docs |
| **Health** | http://localhost:8000/health |
| **Neo4j Browser** | http://localhost:7474 (`neo4j` / `ragplatform`) |
| **Prometheus** | http://localhost:9090 |

Stop:

```bash
docker compose down
```

**Requirements:** Docker Desktop with **6GB+** memory; an OpenAI-compatible LLM API key.  
Ops, troubleshooting, and reset procedures: **[RUNBOOK.md](RUNBOOK.md)**.

---

## Architecture (overview)

```
User → React UI → FastAPI
                    ├─ Router → Vector (FAISS) | Hybrid (FAISS+BM25+rerank) | Graph (Neo4j)
                    └─ GenerateService → External LLM (citations)
Ingest → chunk → corpus.jsonl + FAISS + BM25 (+ optional graph extract)
```

Full diagram and Mermaid charts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

![Architecture diagram](docs/architecture.png)

---

## Executive summary

Internal teams struggle to get quick, trustworthy answers from scattered documents — specs, wikis, notes, and reports. Building a custom search stack for every corpus is slow and requires expertise most small teams do not have.

This platform lets anyone **upload their own documents**, ask questions in plain language, and receive answers **backed by retrieved source chunks**. It is multipurpose: the same stack supports fact lookup, cross-document questions, and org-graph questions (people, projects, reporting lines).

It is demonstrated on a simulated company corpus derived from [EnterpriseRAG-Bench](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench) (MIT). See the [Dataset & Model Card](DATASET_CARD.md) for data and model details, and the [Executive Briefing](EXECUTIVE_BRIEFING.md) for problem, results, and risks.

**Bottom line:** Faster, more trustworthy answers from internal knowledge — with one Docker command and no custom pipeline per dataset.

---

## Evaluation snapshot

From `data/eval_results.json` (150 stratified queries, 3 seeds):

| Criterion | Target | Result |
|-----------|--------|--------|
| Grounding precision | ≥ 0.75 | **0.81** |
| Mean latency | ≤ 5.0 s | **3.00 s** |
| Router accuracy | ≥ 0.80 | **0.91** |
| F1 vs gold | — | **0.84** |

Details: [EXECUTIVE_BRIEFING.md](EXECUTIVE_BRIEFING.md#5-key-results-evaluation).

---

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

Covers health, query API wiring, and router behaviour under `tests/`.

---

## Project layout (short)

```
app/           # FastAPI backend (routers + services)
frontend/      # React UI
data/seed/     # Corpus + graph seed
data/index/    # FAISS + BM25
scripts/       # Index build, eval, seed fetch
tests/         # pytest
docs/          # Architecture diagram + notes
docker-compose.yml
```

---

## License

See [LICENSE](LICENSE). Seed dataset attribution: [data/seed/LICENSE.txt](data/seed/LICENSE.txt).
