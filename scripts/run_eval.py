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

Grounding metric (Success Criterion 1): per-example *citation precision*
  |citations ∩ gold source_chunk_ids| / |citations|
(0.0 if the API returns no citations). The reported grounding_precision is
the mean of those per-example scores. This matches the criterion name better
than the old binary "all citations ⊆ gold" check, which scored 0 whenever
top-k retrieval included any non-gold chunk.

Load control (Groq free/on-demand TPM is tight, ~6k tokens/min):
  - Default concurrency is 1 (one /query in flight) so we do not burst LLM calls.
  - Default HTTP timeout is 180s so Groq client retries can finish.
  - Default --request-delay is 15s so successive large prompts stay under TPM.
  Raise --concurrency only if your provider tier allows it.
"""

import argparse
import asyncio
import json
import math
import random
import statistics
import string
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import httpx

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_set.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_results.json"
DEFAULT_API_BASE_URL = "http://localhost:8000"
# Low-load defaults: Groq on_demand ~6000 TPM; ~2k tokens/request ⇒ ~3 req/min max.
DEFAULT_CONCURRENCY = 1
DEFAULT_TIMEOUT_SECONDS = 180.0
# Pause after each /query before the next starts (same concurrency slot).
# ~15s keeps large-context generations under ~6k TPM; raise if 429s continue.
DEFAULT_REQUEST_DELAY_SECONDS = 15.0
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


# Target mix for a smaller, strategy-balanced eval (deadline / free-tier runs).
STRATIFIED_STRATEGIES = ("vector", "hybrid", "graph")
DEFAULT_PER_STRATEGY = 50


def stratified_by_expected_strategy(
    examples: list[dict],
    per_strategy: int = DEFAULT_PER_STRATEGY,
    strategies: tuple[str, ...] = STRATIFIED_STRATEGIES,
    sample_seed: int = 42,
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    """Sample up to `per_strategy` examples per expected_strategy.

    Deterministic shuffle (sample_seed). If a strategy has fewer examples than
    requested, takes all of them and records the shortfall.
    Returns (selected, taken_counts, available_counts).
    """
    if per_strategy < 1:
        raise ValueError(f"per_strategy must be >= 1, got {per_strategy}")

    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for ex in examples:
        by_strategy[str(ex.get("expected_strategy", "unknown"))].append(ex)

    available = {s: len(by_strategy.get(s, [])) for s in strategies}
    rng = random.Random(sample_seed)
    selected: list[dict] = []
    taken: dict[str, int] = {}

    for strategy in strategies:
        pool = list(by_strategy.get(strategy, []))
        rng.shuffle(pool)
        n = min(per_strategy, len(pool))
        chosen = pool[:n]
        taken[strategy] = n
        selected.extend(chosen)
        if n < per_strategy:
            print(
                f"  WARNING: expected_strategy={strategy!r} has only {len(pool)} "
                f"examples (wanted {per_strategy}); using {n}."
            )

    # Stable order: strategy groups in STRATIFIED_STRATEGIES order (already appended that way).
    return selected, taken, available


def citation_precision(citations: list[str], expected_chunk_ids: list[str]) -> float:
    """Citation precision: fraction of returned citations that appear in gold.

    Returns 0.0 when there are no citations (cannot be grounded). Duplicates
    in `citations` are counted once each toward both numerator and
    denominator so a repeated wrong id still hurts precision.
    """
    if not citations:
        return 0.0
    gold = set(expected_chunk_ids)
    hits = sum(1 for c in citations if c in gold)
    return hits / len(citations)


# Back-compat alias for anything that still imports the old name.
def judge_grounded(citations: list[str], expected_chunk_ids: list[str]) -> float:
    return citation_precision(citations, expected_chunk_ids)


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


def _result_from_example(
    example: dict, result: Optional[dict]
) -> dict:
    """Build one raw result dict for an example (same schema as before)."""
    if result is None:
        return {
            "question": example["question"],
            "expected_strategy": example["expected_strategy"],
            "query_pattern": example["query_pattern"],
            "strategy_used": "error",
            "grounded": 0.0,  # citation precision
            "f1": 0.0,
            "latency": float("nan"),
            "error": True,
        }

    # `grounded` holds per-example citation precision in [0, 1]; aggregation
    # mean(grounded) is the reported grounding_precision.
    grounded = citation_precision(result["citations"], example["source_chunk_ids"])
    f1 = token_f1(result["answer"], example["expected_answer"])

    return {
        "question": example["question"],
        "expected_strategy": example["expected_strategy"],
        "query_pattern": example["query_pattern"],
        "strategy_used": result["strategy_used"],
        "grounded": grounded,
        "f1": f1,
        "latency": result["latency"],
        "error": False,
    }


async def run_single_pass(
    client: httpx.AsyncClient,
    examples: list[dict],
    forced_strategy: Optional[str],
    seed: int,
    concurrency: int = DEFAULT_CONCURRENCY,
    request_delay: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> list[dict]:
    """Runs every example once, either routed (forced_strategy=None, the
    router decides) or pinned to a fixed strategy (forced_strategy="vector"
    for the baseline pass), all under the same generation `seed`.

    Examples are issued with at most `concurrency` in flight. After each
    /query returns, waits `request_delay` seconds before releasing the slot
    so the next request does not immediately re-hit provider TPM limits.
    Results are returned in the same order as `examples`.
    """
    if concurrency < 1:
        raise ValueError(f"concurrency must be >= 1, got {concurrency}")
    if request_delay < 0:
        raise ValueError(f"request_delay must be >= 0, got {request_delay}")

    semaphore = asyncio.Semaphore(concurrency)
    done = 0
    total = len(examples)
    progress_lock = asyncio.Lock()

    async def _one(example: dict) -> dict:
        nonlocal done
        async with semaphore:
            result = await _call_query(client, example["question"], forced_strategy, seed)
            # Pace after the call so Groq TPM can drain before the next query.
            if request_delay > 0:
                await asyncio.sleep(request_delay)
        row = _result_from_example(example, result)
        async with progress_lock:
            done += 1
            if done == total or done % 25 == 0:
                print(f"    progress {done}/{total}", flush=True)
        return row

    # asyncio.gather preserves input order.
    return list(await asyncio.gather(*[_one(ex) for ex in examples]))


def _log_pass_timing(label: str, wall_seconds: float, raw_results: list[dict]) -> None:
    """Print wall-clock and per-request latency summary for a pass (not saved)."""
    valid_latencies = [r["latency"] for r in raw_results if not r["error"]]
    n_errors = sum(1 for r in raw_results if r["error"])
    if valid_latencies:
        mean_lat = statistics.mean(valid_latencies)
        sorted_lat = sorted(valid_latencies)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95 = sorted_lat[min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))]
        print(
            f"  [{label}] wall={wall_seconds:.2f}s  "
            f"req_mean={mean_lat:.3f}s  req_p50={p50:.3f}s  req_p95={p95:.3f}s  "
            f"n={len(raw_results)}  errors={n_errors}"
        )
    else:
        print(f"  [{label}] wall={wall_seconds:.2f}s  all {len(raw_results)} requests failed")


async def _warmup(
    client: httpx.AsyncClient, examples: list[dict], seed: int
) -> None:
    """One untimed request so cold-start does not dominate the first examples.
    Excluded from saved metrics.
    """
    if not examples:
        return
    print("Warm-up request (excluded from metrics)...")
    start = time.perf_counter()
    result = await _call_query(client, examples[0]["question"], forced_strategy=None, seed=seed)
    elapsed = time.perf_counter() - start
    status = "ok" if result is not None else "failed"
    print(f"  Warm-up {status} in {elapsed:.2f}s")


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
            "mean_latency": (statistics.mean(r["latency"] for r in valid)) if valid else None,
        }
    return out


def _overall_metrics(raw_results: list[dict]) -> dict:
    valid = [r for r in raw_results if not r["error"]]
    if not valid:
        return {
            "grounding_precision": 0.0,
            "f1": 0.0,
            "mean_latency": None,
            "n_errors": len(raw_results),
            "n_valid": 0,
        }
    return {
        "grounding_precision": sum(r["grounded"] for r in valid) / len(valid),
        "f1": statistics.mean(r["f1"] for r in valid),
        "mean_latency": statistics.mean(r["latency"] for r in valid),
        "n_errors": len(raw_results) - len(valid),
        "n_valid": len(valid),
    }


def _router_accuracy(raw_results: list[dict]) -> float:
    valid = [r for r in raw_results if not r["error"]]
    if not valid:
        return 0.0
    correct = sum(1 for r in valid if r["strategy_used"] == r["expected_strategy"])
    return correct / len(valid)


def _mean_std(values: list[float]) -> dict:
    """Mean/std over finite numbers only (all-error runs use NaN latency)."""
    finite = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if not finite:
        return {"mean": None, "std": None}
    if len(finite) == 1:
        return {"mean": finite[0], "std": 0.0}
    return {"mean": statistics.mean(finite), "std": statistics.pstdev(finite)}


def _parse_seeds(value: str) -> list[int]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("seeds must be a comma-separated list of ints")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid seeds: {value}") from exc


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the held-out eval set against /query and write data/eval_results.json. "
            "Defaults are low-load (concurrency=1, delay=15s) for Groq TPM limits. "
            "Use --deadline after switching to Gemini for a same-day full-set run."
        )
    )
    parser.add_argument(
        "--deadline",
        action="store_true",
        help=(
            "Same-day eval profile: 1 seed, concurrency=1, request-delay=1s, timeout=90, "
            "and stratified sample 50 vector / 50 hybrid / 50 graph (or all available). "
            "Safe for Cerebras free; override flags if your tier allows more load."
        ),
    )
    parser.add_argument(
        "--per-strategy",
        type=int,
        default=None,
        help=(
            f"Sample up to N examples per expected_strategy "
            f"(vector/hybrid/graph). Default with --deadline: {DEFAULT_PER_STRATEGY}. "
            "Omit for the full eval set."
        ),
    )
    parser.add_argument(
        "--full-set",
        action="store_true",
        help="Use the full eval set even with --deadline (disables stratified sampling).",
    )
    parser.add_argument(
        "--seeds",
        type=_parse_seeds,
        default=None,
        help=f"Comma-separated seeds (default: {','.join(str(s) for s in SEEDS)}).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help=(
            f"Max in-flight /query requests per pass "
            f"(default: {DEFAULT_CONCURRENCY}; keep at 1 on Groq free/on_demand)."
        ),
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=None,
        help=(
            f"Seconds to wait after each /query before starting the next "
            f"(default: {DEFAULT_REQUEST_DELAY_SECONDS} for Groq). "
            "Use 0 with Gemini/Cerebras; raise if you still see TPM 429s."
        ),
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"API base URL (default: {DEFAULT_API_BASE_URL}).",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip the untimed warm-up request before seeded runs.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help=f"HTTP client timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    return parser.parse_args(argv)


def _resolve_run_config(
    args: argparse.Namespace,
) -> tuple[list[int], int, float, float, Optional[int]]:
    """Apply defaults and --deadline overrides. Returns per_strategy or None for full set."""
    if args.deadline:
        # Cerebras free still rate-limits; concurrency=1 + light pacing avoids mass 429s.
        seeds = args.seeds if args.seeds is not None else [42]
        concurrency = args.concurrency if args.concurrency is not None else 1
        request_delay = args.request_delay if args.request_delay is not None else 1.0
        timeout = args.timeout if args.timeout is not None else 90.0
        if args.full_set:
            per_strategy = None
        elif args.per_strategy is not None:
            per_strategy = args.per_strategy
        else:
            per_strategy = DEFAULT_PER_STRATEGY
    else:
        seeds = args.seeds if args.seeds is not None else list(SEEDS)
        concurrency = args.concurrency if args.concurrency is not None else DEFAULT_CONCURRENCY
        request_delay = (
            args.request_delay if args.request_delay is not None else DEFAULT_REQUEST_DELAY_SECONDS
        )
        timeout = args.timeout if args.timeout is not None else DEFAULT_TIMEOUT_SECONDS
        per_strategy = args.per_strategy  # None => full set unless explicitly set
    return seeds, concurrency, request_delay, timeout, per_strategy


async def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    seeds, concurrency, request_delay, timeout, per_strategy = _resolve_run_config(args)

    if concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    if request_delay < 0:
        raise SystemExit("--request-delay must be >= 0")
    if timeout <= 0:
        raise SystemExit("--timeout must be > 0")
    if not seeds:
        raise SystemExit("at least one seed is required")
    if per_strategy is not None and per_strategy < 1:
        raise SystemExit("--per-strategy must be >= 1")

    all_examples = load_eval_set()
    sample_meta: dict = {"full_set_size": len(all_examples), "stratified": False}

    if per_strategy is not None:
        print(
            f"Stratified sample: up to {per_strategy} per expected_strategy "
            f"({', '.join(STRATIFIED_STRATEGIES)}) from {len(all_examples)} total."
        )
        examples, taken, available = stratified_by_expected_strategy(
            all_examples, per_strategy=per_strategy, sample_seed=42
        )
        sample_meta.update(
            {
                "stratified": True,
                "per_strategy_target": per_strategy,
                "available_by_strategy": available,
                "taken_by_strategy": taken,
                "sample_seed": 42,
            }
        )
        print(f"  available={available}")
        print(f"  taken={taken}  total_selected={len(examples)}")
    else:
        examples = all_examples

    print(
        f"Running on {len(examples)} eval examples. "
        f"seeds={seeds} concurrency={concurrency} request_delay={request_delay}s "
        f"timeout={timeout}s api={args.api_base_url}"
    )
    if args.deadline:
        print(
            "Deadline mode: light load "
            f"(concurrency={concurrency}, delay={request_delay}s)."
        )
    elif concurrency == 1 and request_delay > 0:
        print("Low-load mode: one /query at a time with pacing (Groq ~6k TPM).")

    routed_runs = []
    baseline_runs = []
    eval_wall_start = time.perf_counter()

    async with httpx.AsyncClient(base_url=args.api_base_url, timeout=timeout) as client:
        if not args.no_warmup:
            await _warmup(client, examples, seed=seeds[0])
            if request_delay > 0:
                await asyncio.sleep(request_delay)

        for i, seed in enumerate(seeds, start=1):
            print(f"Seeded run {i}/{len(seeds)} (seed={seed}, routed, router decides)...")
            t0 = time.perf_counter()
            routed = await run_single_pass(
                client,
                examples,
                forced_strategy=None,
                seed=seed,
                concurrency=concurrency,
                request_delay=request_delay,
            )
            _log_pass_timing(f"routed seed={seed}", time.perf_counter() - t0, routed)
            routed_runs.append(routed)

            print(f"Seeded run {i}/{len(seeds)} (seed={seed}, baseline: vector-only, M8 reference)...")
            t0 = time.perf_counter()
            baseline = await run_single_pass(
                client,
                examples,
                forced_strategy="vector",
                seed=seed,
                concurrency=concurrency,
                request_delay=request_delay,
            )
            _log_pass_timing(f"baseline seed={seed}", time.perf_counter() - t0, baseline)
            baseline_runs.append(baseline)

    total_wall = time.perf_counter() - eval_wall_start
    print(f"\nTotal eval wall-clock: {total_wall:.2f}s")

    routed_overall = [_overall_metrics(r) for r in routed_runs]
    baseline_overall = [_overall_metrics(r) for r in baseline_runs]
    routed_router_acc = [_router_accuracy(r) for r in routed_runs]

    grounding_stats = _mean_std([m["grounding_precision"] for m in routed_overall])
    f1_stats = _mean_std([m["f1"] for m in routed_overall])
    latency_stats = _mean_std(
        [m["mean_latency"] for m in routed_overall if m.get("mean_latency") is not None]
    )
    router_acc_stats = _mean_std(routed_router_acc)

    baseline_grounding_stats = _mean_std([m["grounding_precision"] for m in baseline_overall])
    baseline_f1_stats = _mean_std([m["f1"] for m in baseline_overall])
    baseline_latency_stats = _mean_std(
        [m["mean_latency"] for m in baseline_overall if m.get("mean_latency") is not None]
    )

    total_errors = sum(m.get("n_errors", 0) for m in routed_overall)
    total_valid = sum(m.get("n_valid", 0) for m in routed_overall)

    # Per-strategy / per-query-pattern breakdown from the LAST routed run
    # (representative single-run breakdown; seeded variance is already
    # captured in the top-line mean/std stats above).
    last_routed = routed_runs[-1]
    by_strategy = _aggregate_by(last_routed, "strategy_used")
    by_pattern = _aggregate_by(last_routed, "query_pattern")

    g_mean = grounding_stats["mean"]
    l_mean = latency_stats["mean"]
    r_mean = router_acc_stats["mean"]

    # Same schema as before (meta keys that consumers already rely on).
    results = {
        "meta": {
            "num_examples": len(examples),
            "seeds": seeds,
            "api_base_url": args.api_base_url,
            "n_valid_routed": total_valid,
            "n_errors_routed": total_errors,
            "sample": sample_meta,
            "expected_strategy_counts": dict(Counter(e["expected_strategy"] for e in examples)),
        },
        "success_criteria": {
            "criterion_1_grounding_precision": {
                **grounding_stats,
                "target": GROUNDING_PRECISION_TARGET,
                "pass": g_mean is not None and g_mean >= GROUNDING_PRECISION_TARGET,
            },
            "criterion_2_latency_seconds": {
                **latency_stats,
                "target": MAX_LATENCY_SECONDS,
                "pass": l_mean is not None and l_mean < MAX_LATENCY_SECONDS,
            },
            "criterion_3_router_accuracy": {
                **router_acc_stats,
                "target": ROUTER_ACCURACY_TARGET,
                "pass": r_mean is not None and r_mean >= ROUTER_ACCURACY_TARGET,
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
    print(f"Routed valid={total_valid} errors={total_errors}")
    print(json.dumps(results["success_criteria"], indent=2))
    if total_errors > 0:
        print(
            "\nWARNING: errors present — metrics exclude failed requests. "
            "Re-run with lower load if error rate is high:\n"
            "  python scripts/run_eval.py --deadline --concurrency 1 --request-delay 2"
        )


if __name__ == "__main__":
    asyncio.run(main())
