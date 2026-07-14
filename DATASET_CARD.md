# Dataset & Model Card — Multipurpose RAG System

This card covers (A) the **seed / evaluation data** shipped with the project and (B) the **models** used at runtime.  
Format inspired by Hugging Face Dataset and Model Card conventions.

---

# A. Dataset Card

## A.1 Dataset summary

| Field | Value |
|-------|--------|
| **Name (project use)** | Capstone multipurpose RAG seed corpus |
| **Primary source** | [onyx-dot-app/EnterpriseRAG-Bench](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench) |
| **License (upstream)** | MIT (see `data/seed/LICENSE.txt`) |
| **Language** | English |
| **Domain** | Simulated enterprise internal knowledge (planning, engineering, sales, support style text) |
| **Intended use in this project** | Demo corpus for retrieval + generation; offline evaluation |

## A.2 Motivation

Enterprise RAG evaluation needs multi-document, multi-entity content. EnterpriseRAG-Bench provides a public, MIT-licensed bench corpus suitable for teaching multipurpose retrieval (vector / hybrid / graph) without real corporate secrets or personal data.

## A.3 Composition

### Shipped artifacts

| Artifact | Path | Description |
|----------|------|-------------|
| Chunk corpus | `data/seed/corpus.jsonl` | One JSON object per chunk (text + metadata). ~5k lines after project processing |
| Graph seed | `data/seed/graph_seed.json` | People, projects, relationships extracted for Neo4j |
| Entity extraction side file | `data/seed/extracted_entities.json` | Intermediate extraction output |
| Prebuilt FAISS index | `data/index/corpus.faiss` | Dense vectors for seed corpus |
| Chunk metadata | `data/index/corpus_meta.jsonl` | Aligns FAISS rows to chunks |
| BM25 index | `data/index/corpus_bm25.pkl` | Keyword index |
| Eval questions | `data/eval_set.jsonl` | Labeled eval queries (strategy / gold) |
| Eval results | `data/eval_results.json` | Last recorded metric snapshot |
| Upload side-cars | `data/uploads/` | User-ingest manifests and chunk dumps |

### Graph seed (approx. counts from `graph_seed.json`)

| Entity / relation | Count |
|-------------------|-------|
| People | 88 |
| Projects | 22 |
| `reports_to` | 18 |
| `owns` | 27 |
| `works_on` | 41 |
| `collaborates_with` | 60 |

Runtime Neo4j is seeded from this file on container start (idempotent MERGE).

### Chunking (project pipeline)

- Target chunk size ~**1500** characters  
- Overlap ~**200** characters  
- Sources: seed download script, file upload (PDF/DOCX/CSV/TXT), URL / HuggingFace ingest  

## A.4 Collection and processing

1. Seed material is obtained from EnterpriseRAG-Bench (see `scripts/fetch_seed_data.py`).  
2. Text is chunked and written to `corpus.jsonl`.  
3. Embeddings (`all-MiniLM-L6-v2`) build FAISS; full corpus rebuilds BM25.  
4. Structured people/project links are materialised into `graph_seed.json` and Neo4j.  
5. Evaluation questions are curated / generated into `data/eval_set.jsonl` (150 stratified items across vector / hybrid / graph).

**User-uploaded data** (via UI/API) is stored under `data/` on the machine running Docker. It is **not** sent to the project maintainers. Uploaded content may be sent to the **configured LLM provider** at query time for answer generation and optional entity extraction.

## A.5 Recommended uses

- Capstone demo and grader evaluation  
- Regression of router + retrieval strategies  
- Teaching hybrid RAG + NL→Cypher graph RAG  

## A.6 Out-of-scope / not recommended

- Production use as a real company knowledge base without legal review  
- Treating entity names as real persons (synthetic / bench content)  
- High-stakes decisions (medical, legal, safety) without human verification  
- Scraping or re-publishing third-party data beyond the upstream license  

## A.7 Distribution and maintenance

| Item | Detail |
|------|--------|
| Hosted with | This GitHub repository |
| Upstream updates | Re-run fetch/build scripts if refreshing seed |
| Contact | Team Builders — see [TEAM_CONTRACT.md](TEAM_CONTRACT.md) |

## A.8 Known limitations and risks

- Bench text may not match a real org’s jargon or structure.  
- Graph coverage is partial (extracted subset of entities/relations).  
- Eval set is project-constructed; metrics are **not** a public leaderboard claim.  
- User uploads may contain sensitive data if operators put it there — operators own that risk.  
- LLM answers can still be incomplete even when retrieval is correct.

## A.9 Citation / attribution

```
Dataset: onyx-dot-app/EnterpriseRAG-Bench
URL: https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench
License: MIT
Local attribution file: data/seed/LICENSE.txt
```

---

# B. Model Card (runtime models)

The system does **not** train a new foundation model. It composes open embedding/rerank models with an external chat LLM.

## B.1 Models used

| Role | Model / service | Notes |
|------|-----------------|--------|
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | Dense vectors for FAISS |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Hybrid path re-scoring |
| **Chat / generation** | OpenAI-compatible API | Configured via env (Cerebras / Groq / Gemini, etc.) |
| **NL → Cypher** | Same chat LLM | Graph strategy |
| **Optional entity extract** | Same chat LLM | On ingest when graph enabled |

Config knobs live in `app/core/config.py` and `.env.example` (e.g. `cross_encoder_model`, `llm_api_base`, `llm_model`).

### Example LLM configurations (`.env.example`)

| Provider | Base URL | Example model |
|----------|----------|---------------|
| Cerebras (recommended for full eval) | `https://api.cerebras.ai/v1` | `gpt-oss-120b` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` |
| Gemini (OpenAI-compatible) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` |

## B.2 Intended use

- Grounded Q&A over the project corpus and user-ingested documents  
- Strategy routing among vector / hybrid / graph retrieval  
- Local demo and evaluation, not unattended enterprise production without further hardening  

## B.3 Factors and performance snapshot

Held-out style eval (150 queries, 3 seeds) — see `data/eval_results.json` and [EXECUTIVE_BRIEFING.md](EXECUTIVE_BRIEFING.md):

| Metric | Mean |
|--------|------|
| Grounding precision | 0.81 |
| Latency | 3.00 s |
| Router accuracy | 0.91 |
| F1 vs gold answer | 0.84 |

Performance depends heavily on **LLM provider latency/rate limits** and **hardware** for local embedding/rerank.

## B.4 Ethical considerations

- **Privacy:** User documents and queries may leave the host when sent to a third-party LLM API. Use providers and keys under your organisation’s policy.  
- **Bias:** Upstream bench text and general-purpose LLMs can reflect societal and domain biases.  
- **Safety:** No specialized safety layer beyond prompt grounding; do not use for harmful instructions.  
- **Transparency:** Answers include chunk citations where the pipeline succeeds.

## B.5 Environmental considerations

- Local: CPU/GPU for MiniLM + cross-encoder load on API container.  
- Remote: Chat tokens billed / free-tier limited at the LLM provider.  
- Neo4j + Docker stack add always-on memory (~6GB+ recommended).

## B.6 Caveats and recommendations

1. Prefer **hybrid** for ambiguous questions (router already falls back when confidence is low).  
2. Keep graph password empty only if you intentionally disable graph retrieval.  
3. Re-run `scripts/run_eval.py` after major retrieval or prompt changes.  
4. Document any fine-tuned models here if Component/Module work replaces the stock cross-encoder.

---

# C. Quick links

| Doc | Path |
|-----|------|
| Executive briefing | [EXECUTIVE_BRIEFING.md](EXECUTIVE_BRIEFING.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Runbook | [RUNBOOK.md](RUNBOOK.md) |
| Workflow detail | [WORKFLOW.md](WORKFLOW.md) |
