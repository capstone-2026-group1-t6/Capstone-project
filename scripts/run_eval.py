"""Eval harness: runs the held-out QA set through the API and reports the
metrics from the Evaluation plan.

  - Success Criterion 1: grounding precision >= 0.75
  - Success Criterion 2: end-to-end query latency < 5s (up to ~5k chunks)
  - Success Criterion 3 (optional): router picks the correct strategy for
    >= 80% of held-out queries
  - Primary metric: grounding precision + F1 vs. gold_answer, plus latency
    and router accuracy
  - Stochastic components: generation is stochastic -> run >= 3 seeded runs,
    report mean +/- standard deviation
  - Error analysis dimensions: (1) retrieval strategy actually used by the
    router, (2) query pattern type
  - Baseline: plain vector search without rerank/routing (M8 reference
    impl), run over the FULL eval set for comparison

IMPORTANT FIX vs. the original scaffold: the routed pass below does NOT set
`forced_strategy`, so RouterService actually makes its own decision on each
call. The original draft forced `expected_strategy` on every request, which
made Success Criterion 3 (router accuracy) impossible to measure -- the
router never got a chance to choose. `forced_strategy` is now only used for
the separate baseline pass (always "vector", per the M8 reference impl).

ASSUMPTION: the /query endpoint's JSON response includes a `strategy_used`
field naming the strategy the router actually selected, alongside `answer`
and `citations`. If app/routers/query.py names this field differently,
update STRATEGY_USED_FIELD below to match.

This is still a scaffold in one sense: `judge_grounded()` is a stand-in for
whatever grounding judge the team lands on (rule-based citation-overlap
check first, LLM-judge later) -- swap its implementation without touching
anything else in this file.
"""

import asyncio
import json
import statistics
import string
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_set.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_results.json"
API_BASE_URL = "http://localhost:8000"
# Concrete seed values actually sent to /query so each "seeded run" is
# genuinely different and, in principle, reproducible on its own (rerunning
# seed=42 should give the same generation as before, modulo any
# non-determinism in the underlying LLM API itself).
SEEDS = [42, 123, 2024]
STRATEGY_USED_FIELD = "strategy_used"  # adjust if app/routers/query.py names it differently
SEED_FIELD = "seed"  # adjust if app/routers/query.py expects a different key/location

# Success criteria, straight from the proposal.
GROUNDING_PRECISION_TARGET = 0.75
MAX_LATENCY_SECONDS = 5.0
ROUTER_ACCURACY_TARGET = 0.80


def load_eval_set() -> list[dict]:
    if not EVAL_SET_PATH.exists():
        raise FileNotFoundError(
            f"{EVAL_SET_PATH} not found — build it first (see scripts/build_eval_set.py)."
        )
    with EVAL_SET_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def judge_grounded(citations: list[str], expected_chunk_ids: list[str]) -> bool:
    """Placeholder grounding judge: are the returned citations a subset of the
    expected source chunks? Swap for a stricter check or LLM-judge later.
    """
    if not citations:
        return False
    return set(citations).issubset(set(expected_chunk_ids))


_ARTICLES = {"a", "an", "the"}


def _normalize_text(text: str) -> list[str]:
    text = text.lower()
    text = "".join(ch for ch in text if ch not in string.punctuation)
    return [t for t in text.split() if t not in _ARTICLES]


def token_f1(prediction: str, gold: str) -> float:
    """SQuAD-style token-overlap F1 between a predicted and gold answer."""
    pred_tokens = _normalize_text(prediction)
    gold_tokens = _normalize_text(gold)

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    pred_counts: dict[str, int] = defaultdict(int)
    for t in pred_tokens:
        pred_counts[t] += 1
    gold_counts: dict[str, int] = defaultdict(int)
    for t in gold_tokens:
        gold_counts[t] += 1

    overlap = sum(min(count, gold_counts[t]) for t, count in pred_counts.items())
    if overlap == 0:
        return 0.0

    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


async def _call_query(
    client: httpx.AsyncClient, question: str, forced_strategy: Optional[str], seed: int
) -> Optional[dict]:
    payload = {"query": question, SEED_FIELD: seed}
    if forced_strategy is not None:
        payload["forced_strategy"] = forced_strategy

    start = time.perf_counter()
    try:
        response = await client.post("/query", json=payload)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    elapsed = time.perf_counter() - start

    body = response.json()
    return {
        "answer": body.get("answer", ""),
        "citations": body.get("citations", []),
        "strategy_used": body.get(STRATEGY_USED_FIELD, "unknown"),
        "latency": elapsed,
    }


async def run_single_pass(
    client: httpx.AsyncClient, examples: list[dict], forced_strategy: Optional[str], seed: int
) -> list[dict]:
    """Runs every example once, either routed (forced_strategy=None, the
    router decides) or pinned to a fixed strategy (forced_strategy="vector"
    for the baseline pass), all under the same generation `seed`. Returns
    one raw result dict per example.
    """
    raw_results = []
    for example in examples:
        result = await _call_query(client, example["question"], forced_strategy, seed)

        if result is None:
            raw_results.append(
                {
                    "question": example["question"],
                    "expected_strategy": example["expected_strategy"],
                    "query_pattern": example["query_pattern"],
                    "strategy_used": "error",
                    "grounded": False,
                    "f1": 0.0,
                    "latency": float("nan"),
                    "error": True,
                }
            )
            continue

        grounded = judge_grounded(result["citations"], example["source_chunk_ids"])
        f1 = token_f1(result["answer"], example["expected_answer"])

        raw_results.append(
            {
                "question": example["question"],
                "expected_strategy": example["expected_strategy"],
                "query_pattern": example["query_pattern"],
                "strategy_used": result["strategy_used"],
                "grounded": grounded,
                "f1": f1,
                "latency": result["latency"],
                "error": False,
            }
        )
    return raw_results


def _aggregate_by(raw_results: list[dict], key: str) -> dict:
    grouped = defaultdict(list)
    for r in raw_results:
        grouped[r[key]].append(r)

    out = {}
    for group_value, rows in grouped.items():
        valid = [r for r in rows if not r["error"]]
        out[group_value] = {
            "n": len(rows),
            "grounding_precision": (sum(r["grounded"] for r in valid) / len(valid)) if valid else 0.0,
            "f1": (statistics.mean(r["f1"] for r in valid)) if valid else 0.0,
            "mean_latency": (statistics.mean(r["latency"] for r in valid)) if valid else float("nan"),
        }
    return out


def _overall_metrics(raw_results: list[dict]) -> dict:
    valid = [r for r in raw_results if not r["error"]]
    if not valid:
        return {"grounding_precision": 0.0, "f1": 0.0, "mean_latency": float("nan"), "n_errors": len(raw_results)}
    return {
        "grounding_precision": sum(r["grounded"] for r in valid) / len(valid),
        "f1": statistics.mean(r["f1"] for r in valid),
        "mean_latency": statistics.mean(r["latency"] for r in valid),
        "n_errors": len(raw_results) - len(valid),
    }


def _router_accuracy(raw_results: list[dict]) -> float:
    valid = [r for r in raw_results if not r["error"]]
    if not valid:
        return 0.0
    correct = sum(1 for r in valid if r["strategy_used"] == r["expected_strategy"])
    return correct / len(valid)


def _mean_std(values: list[float]) -> dict:
    return {"mean": statistics.mean(values), "std": statistics.pstdev(values)}


async def main() -> None:
    examples = load_eval_set()
    print(f"Loaded {len(examples)} eval examples.")

    routed_runs = []
    baseline_runs = []

    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        for i, seed in enumerate(SEEDS, start=1):
            print(f"Seeded run {i}/{len(SEEDS)} (seed={seed}, routed, router decides)...")
            routed_runs.append(await run_single_pass(client, examples, forced_strategy=None, seed=seed))

            print(f"Seeded run {i}/{len(SEEDS)} (seed={seed}, baseline: vector-only, M8 reference)...")
            baseline_runs.append(await run_single_pass(client, examples, forced_strategy="vector", seed=seed))

    routed_overall = [_overall_metrics(r) for r in routed_runs]
    baseline_overall = [_overall_metrics(r) for r in baseline_runs]
    routed_router_acc = [_router_accuracy(r) for r in routed_runs]

    grounding_stats = _mean_std([m["grounding_precision"] for m in routed_overall])
    f1_stats = _mean_std([m["f1"] for m in routed_overall])
    latency_stats = _mean_std([m["mean_latency"] for m in routed_overall])
    router_acc_stats = _mean_std(routed_router_acc)

    baseline_grounding_stats = _mean_std([m["grounding_precision"] for m in baseline_overall])
    baseline_f1_stats = _mean_std([m["f1"] for m in baseline_overall])
    baseline_latency_stats = _mean_std([m["mean_latency"] for m in baseline_overall])

    # Per-strategy / per-query-pattern breakdown from the LAST routed run
    # (representative single-run breakdown; seeded variance is already
    # captured in the top-line mean/std stats above).
    last_routed = routed_runs[-1]
    by_strategy = _aggregate_by(last_routed, "strategy_used")
    by_pattern = _aggregate_by(last_routed, "query_pattern")

    results = {
        "meta": {
            "num_examples": len(examples),
            "seeds": SEEDS,
            "api_base_url": API_BASE_URL,
        },
        "success_criteria": {
            "criterion_1_grounding_precision": {
                **grounding_stats,
                "target": GROUNDING_PRECISION_TARGET,
                "pass": grounding_stats["mean"] >= GROUNDING_PRECISION_TARGET,
            },
            "criterion_2_latency_seconds": {
                **latency_stats,
                "target": MAX_LATENCY_SECONDS,
                "pass": latency_stats["mean"] < MAX_LATENCY_SECONDS,
            },
            "criterion_3_router_accuracy": {
                **router_acc_stats,
                "target": ROUTER_ACCURACY_TARGET,
                "pass": router_acc_stats["mean"] >= ROUTER_ACCURACY_TARGET,
            },
        },
        "f1_vs_gold_answer": f1_stats,
        "baseline_vector_only_m8": {
            "grounding_precision": baseline_grounding_stats,
            "f1": baseline_f1_stats,
            "mean_latency": baseline_latency_stats,
        },
        "by_strategy": by_strategy,
        "by_query_pattern": by_pattern,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\nSaved full results to {RESULTS_PATH}")
    print(json.dumps(results["success_criteria"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())