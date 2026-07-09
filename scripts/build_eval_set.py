"""Scaffold for the held-out QA set described in the Evaluation plan:

  - >= 50 hand-validated examples per retrieval strategy (~150 total)
  - each example tagged with query_pattern: lookup | cross_document | entity_relationship
  - each example tagged with expected_strategy: vector | hybrid | graph

Team members write and cross-check question/answer pairs against the seed
corpus (see fetch_seed_data.py) directly into eval_set.jsonl. This script
just validates the file's shape so a malformed row fails fast in CI rather
than silently breaking eval later.
"""

import json
import sys
from pathlib import Path

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_set.jsonl"

REQUIRED_FIELDS = {"question", "expected_answer", "expected_strategy", "query_pattern", "source_chunk_ids"}
VALID_STRATEGIES = {"vector", "hybrid", "graph"}
VALID_PATTERNS = {"lookup", "cross_document", "entity_relationship"}
MIN_PER_STRATEGY = 50


def validate() -> int:
    if not EVAL_SET_PATH.exists():
        print(f"No eval set yet at {EVAL_SET_PATH}. Nothing to validate.")
        return 0

    counts = {s: 0 for s in VALID_STRATEGIES}
    errors = []

    with EVAL_SET_PATH.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            missing = REQUIRED_FIELDS - row.keys()
            if missing:
                errors.append(f"line {line_number}: missing fields {missing}")
                continue
            if row["expected_strategy"] not in VALID_STRATEGIES:
                errors.append(f"line {line_number}: invalid expected_strategy {row['expected_strategy']!r}")
                continue
            if row["query_pattern"] not in VALID_PATTERNS:
                errors.append(f"line {line_number}: invalid query_pattern {row['query_pattern']!r}")
                continue
            counts[row["expected_strategy"]] += 1

    for strategy, count in counts.items():
        if count < MIN_PER_STRATEGY:
            errors.append(f"only {count}/{MIN_PER_STRATEGY} examples for strategy={strategy}")

    if errors:
        print("Eval set validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"Eval set OK: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
