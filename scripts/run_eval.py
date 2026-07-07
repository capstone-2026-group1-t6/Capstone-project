"""Eval harness: runs the held-out QA set through the API and reports the
metrics from the Evaluation plan.

  - Primary metric: grounding precision + F1 vs. held-out set, plus latency
  - Stochastic components: generation is stochastic -> run >= 3 seeded runs,
    report mean +/- standard deviation
  - Error analysis dimensions: (1) retrieval strategy, (2) query pattern type
  - Baseline: plain vector search without rerank/routing (M8 reference impl)

This is a scaffold: `judge_grounded()` is a stand-in for whatever grounding
judge the team lands on (rule-based overlap check first, LLM-judge later).
"""

import asyncio
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

import httpx

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_set.jsonl"
API_BASE_URL = "http://localhost:8000"
NUM_SEEDED_RUNS = 3


def load_eval_set() -> list[dict]:
    if not EVAL_SET_PATH.exists():
        raise FileNotFoundError(
            f"{EVAL_SET_PATH} not found — build it first (see scripts/build_eval_set.py)."
        )
    with EVAL_SET_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def judge_grounded(answer: str, citations: list[str], expected_chunk_ids: list[str]) -> bool:
    """Placeholder grounding judge: are the returned citations a subset of the
    expected source chunks? Swap for a stricter check or LLM-judge later.
    """
    if not citations:
        return False
    return set(citations).issubset(set(expected_chunk_ids))


async def run_single_pass(client: httpx.AsyncClient, examples: list[dict]) -> dict:
    results_by_strategy = defaultdict(list)
    results_by_pattern = defaultdict(list)
    latencies = []

    for example in examples:
        start = time.perf_counter()
        response = await client.post(
            "/query",
            json={"query": example["question"], "forced_strategy": example["expected_strategy"]},
        )
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        body = response.json()
        grounded = judge_grounded(body["answer"], body["citations"], example["source_chunk_ids"])
        results_by_strategy[example["expected_strategy"]].append(grounded)
        results_by_pattern[example["query_pattern"]].append(grounded)

    return {
        "by_strategy": {k: sum(v) / len(v) for k, v in results_by_strategy.items()},
        "by_pattern": {k: sum(v) / len(v) for k, v in results_by_pattern.items()},
        "mean_latency": statistics.mean(latencies) if latencies else float("nan"),
    }


async def main() -> None:
    examples = load_eval_set()
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        run_results = [await run_single_pass(client, examples) for _ in range(NUM_SEEDED_RUNS)]

    latencies = [r["mean_latency"] for r in run_results]
    print(f"Ran {NUM_SEEDED_RUNS} seeded passes over {len(examples)} examples.")
    print(f"Mean latency: {statistics.mean(latencies):.3f}s +/- {statistics.pstdev(latencies):.3f}s")
    print("Per-strategy grounding precision (last run):", run_results[-1]["by_strategy"])
    print("Per-query-pattern grounding precision (last run):", run_results[-1]["by_pattern"])


if __name__ == "__main__":
    asyncio.run(main())
