# Error Analysis

**Method (left panel):** Offline **FAISS top-5** diagnostic on the 100 eval questions that join free-text gold chunks (`expected_strategy` ∈ {vector, hybrid}).  
**Error** = no gold `source_chunk_ids` appear in top-5 (retrieval miss).  
**Rows** = gold-evidence **length bucket** (total chars of gold chunks / chunk count).  
**Columns** = majority **source type** of those gold chunks (`corpus.jsonl` → `source`).  

Graph-only rows (46 questions, no free-text gold span) use published end-to-end grounding as an **error proxy** (`1 − grounding_precision` from `data/eval_results.json`).

Raw numbers: `data/error_analysis_retrieval.json` · repro: `python scripts/error_analysis_heatmap.py`

---

## Layout

| LEFT — error heatmap | RIGHT — failures + next step |
|----------------------|------------------------------|
| Length × source error rates | 5 documented cases + hypothesis |

---

## LEFT: 2-axis error heatmap

### Retrieval miss rate (top-5, free-text eval)

Cell = **error rate** (share of questions with zero gold chunks in FAISS top-5).  
`(n=…)` = cell sample size. `—` = no eval examples in that cell.

| Evidence length bucket ↓ \ Source type → | **confluence** | **google_drive** | **github** | **gmail** | **fireflies** |
|------------------------------------------|----------------|------------------|------------|-----------|---------------|
| **short** (&lt;2.5k / ≤2 chunks) | **0%** (n=3) | — | **0%** (n=1) | — | — |
| **medium** (2.5–4.5k / 3–4 chunks) | **29%** (n=17) | **18%** (n=11) | **46%** (n=13) | **50%** (n=20) | **55%** (n=11) |
| **long** (&gt;4.5k / 5+ chunks) | **21%** (n=19) | **0%** (n=1) | **0%** (n=1) | **0%** (n=1) | **100%** (n=2) |

**Overall (text eval):** **35%** top-5 miss rate (35 / 100).

### Marginal rates

| Axis | Bucket | Error rate | n |
|------|--------|------------|---|
| Length | short | 0% | 4 |
| Length | medium | **40%** | 72 |
| Length | long | 25% | 24 |
| Source | google_drive | 17% | 12 |
| Source | confluence | 23% | 39 |
| Source | github | 40% | 15 |
| Source | gmail | **48%** | 21 |
| Source | fireflies | **62%** | 13 |

### Graph / structured row (proxy, not FAISS)

| Evidence length bucket | Source type | Error proxy | Basis |
|------------------------|-------------|-------------|--------|
| **graph_struct** (no free-text gold span) | **graph_seed** (Neo4j people/projects) | **14%** | `1 − 0.86` graph-strategy grounding (`eval_results.json`, n=50 graph) |
| (same questions as pattern) | entity_relationship pattern | **25%** | `1 − 0.75` pattern grounding (hardest query pattern) |

### Reading the heatmap

1. **Medium multi-chunk evidence is the danger zone** (40% miss) — most bench questions land here (n=72). Short gold spans are rare but easy when present.  
2. **Meeting + email sources dominate failures** — fireflies **62%**, gmail **48%** vs confluence **23%** / google_drive **17%**. Conversational tone and buried dates/numbers hurt dense MiniLM retrieval.  
3. **GitHub** sits in the middle (**40%**) — product codenames and PR-style wording are sparse in the query.  
4. **Long confluence** is relatively better than medium email/meetings — more redundant technical prose for semantic match.  
5. **Graph path** is stronger on aggregate grounding (14% proxy error) than free-text medium email/meetings, but **entity_relationship** remains the weakest *query pattern* end-to-end (0.75 grounding).

> **Note:** This left panel is a **retrieval** error heatmap (diagnostic). End-to-end system grounding is higher when hybrid + rerank + generation recover (overall grounding precision **0.81** in `eval_results.json`). Sparse long×fireflies cells (n=2) should not be over-interpreted alone.

---

## RIGHT: 5 documented failure cases + next-iteration hypothesis

### Failure case 1 — Meeting transcript + calendar-style facts (fireflies)

| Field | Detail |
|-------|--------|
| **ID** | `qst_0247` |
| **Source / length** | fireflies · medium |
| **Question** | In the partner sales planning call between a vendor and an ISV, what were the concrete due dates in late December for each side to send the pilot inputs and the vendor deliverables? |
| **Gold intent** | Orbital inputs by **12/22**; Redwood co-sell one-pager/pricing by **12/23**; benchmarks by **12/29**. |
| **Failure mode** | Top-5 dense retrieval **missed all gold chunks**. Spoken-style transcript + multi-party commitments; query is abstract (“partner sales planning call”) while evidence uses proper names (Orbital, Redwood). |
| **Impact** | Dates either wrong or invented if generation runs on near-miss neighbors. |

### Failure case 2 — Email thread + compensation exception (gmail)

| Field | Detail |
|-------|--------|
| **ID** | `qst_0288` |
| **Source / length** | gmail · medium |
| **Question** | …rescuing a near-lost senior platform hire… what one-time pay-range exception did People Ops approve (how far above the midpoint)? |
| **Gold intent** | One-time band uplift for INF-324 of **up to 10% above midpoint**. |
| **Failure mode** | Top-5 miss. Long paraphrastic question; key numeric fact is a single clause in an HR email thread. Dense embeddings match “hiring / platform” neighbors, not the exception sentence. |
| **Impact** | High-stakes numeric/policy answer requires exact span; vector-only path is brittle. |

### Failure case 3 — Product codename in rollout design (github)

| Field | Detail |
|-------|--------|
| **ID** | `qst_0180` |
| **Source / length** | github · medium |
| **Question** | …name of the new mechanism that prevents a candidate release from getting full user traffic until a dry run with replayed requests and smoke checks has passed? |
| **Gold intent** | **TrafficEscrow** / `traffic_escrow` service. |
| **Failure mode** | Top-5 miss. Query describes behavior without the rare proper noun; gold PR text is terminology-dense. Pure semantic search under-ranks exact product names. |
| **Impact** | System may describe a related rollout control under the wrong name. |

### Failure case 4 — Multi-step numeric procedure (confluence)

| Field | Detail |
|-------|--------|
| **ID** | `qst_0234` |
| **Source / length** | confluence · medium |
| **Question** | …suggested traffic ramp schedule… small canary to full production, including minimum stabilization wait… |
| **Gold intent** | **10% → 20% → 40% → 80% → 100%**, ≥ **24 hours** between steps. |
| **Failure mode** | Top-5 miss on a structured playbook chunk. Query is long and multi-constraint; embedding may latch onto other “canary / rollout” confluence pages. |
| **Impact** | Partial answers (e.g. only canary %) without the full ramp or wait time. |

### Failure case 5 — Org-graph multi-hop / entity relationship (graph_seed)

| Field | Detail |
|-------|--------|
| **ID** | Pattern: `entity_relationship` (50 eval items; graph strategy n=50) |
| **Source / length** | graph_seed · graph_struct |
| **Representative ask** | Ownership, reporting lines, multi-person project membership (see `TEST_QUERIES.md` graph examples). |
| **Gold intent** | Exact Neo4j-backed person/project relations from `graph_seed.json`. |
| **Failure mode** | Lowest pattern grounding (**0.75**) and F1 (**0.79**) end-to-end. Failures cluster on: (a) **NL→Cypher** mis-translation (wrong relationship type / direction), (b) **name variants** vs seed strings, (c) questions that need multi-hop when the generated Cypher is single-hop, (d) latency pressure (graph mean **3.92 s**). |
| **Impact** | Confident but wrong org chart answers; harder to catch without citation to a free-text chunk. |

---

### Next-iteration hypothesis

**If we had another week, we would try a two-stage “parent-document then chunk” retriever with BM25 date/entity boosts on fireflies + gmail**, because the heatmap shows **medium-length meeting and email evidence at 50–55% top-5 miss** while short structured confluence spans are near **0%** — the bottleneck is not generation alone but **locating the right multi-chunk conversational document before chunk ranking**. Concretely: (1) BM25 + vector retrieve top-N *documents*, (2) re-rank *chunks only inside those docs* with the cross-encoder, (3) add lightweight query expansion for proper nouns and ISO-like dates. We would re-run `scripts/error_analysis_heatmap.py` and full `run_eval.py` and expect the largest drop in fireflies/gmail medium-cell error rates without raising short-doc latency much.

---

## How this connects to system metrics

| Signal | Value | Link to errors |
|--------|-------|----------------|
| Overall grounding precision | 0.81 | Hybrid + rerank + generation recover some retrieval misses |
| Lookup pattern F1 | 0.91 | When gold is found, generation is strong |
| Cross-document grounding | 0.80 | Multi-doc still harder than pure lookup |
| Entity-relationship grounding | 0.75 | Graph/NL→Cypher residual errors |
| Vector-only baseline grounding | 0.71 | Routing + hybrid is material vs pure FAISS |

---

## Reproduce

```bash
# Stack optional for this offline heatmap (needs FAISS index + embeddings model)
python scripts/error_analysis_heatmap.py
# → data/error_analysis_retrieval.json

# Full end-to-end metrics (API must be up)
python scripts/run_eval.py
# → data/eval_results.json
```
