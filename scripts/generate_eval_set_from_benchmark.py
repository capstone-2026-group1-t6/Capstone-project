"""Generates data/eval_set.jsonl from EnterpriseRAG-Bench's real, gold-labeled
question set -- NOT hand-written. Per the Evaluation plan:

  "How the held-out set is built: filtered from the benchmark's existing
   labels rather than hand-written, using question_type and expected_doc_ids
   to assign each question to a strategy."

What this script does:
  1. Loads the full 500-question gold set from HuggingFace
     (onyx-dot-app/EnterpriseRAG-Bench, "questions" split). Real fields:
     question_id, question_type, source_types, question, expected_doc_ids,
     gold_answer, answer_facts.
  2. Excludes "High Level" and "Info Not Found" categories -- per the
     dataset's own documentation, these have NO ground-truth documents, so
     they can't populate `source_chunk_ids` (required by
     scripts/build_eval_set.py).
  3. Keeps only questions whose expected_doc_ids are FULLY covered by the
     local corpus subsample -- i.e. every gold document for that question
     was actually included when scripts/fetch_seed_data.py built our
     ~1k-5k-document subsample. A question with a partially-covered gold
     set can't be fairly graded against our corpus.
  4. Maps each question_type to (query_pattern, expected_strategy) using
     QUESTION_TYPE_MAPPING below.
  5. Resolves each expected_doc_id to the actual chunk_ids covering it,
     using the local corpus_meta.jsonl written by
     app/services/corpus_index.py's CorpusIndex.save().
  6. Writes data/eval_set.jsonl in the exact shape
     scripts/build_eval_set.py already validates -- run that script after
     this one to confirm.

PREREQUISITE: scripts/fetch_seed_data.py and scripts/build_corpus_index.py
must already have run, so data/index/corpus_meta.jsonl exists locally.
This script does not fabricate any question, answer, or document -- it only
filters and relabels the benchmark's own gold data.

PLEASE VERIFY BEFORE TRUSTING THE OUTPUT:
  - QUESTION_TYPE_MAPPING keys are the human-readable category names from
    the dataset card (e.g. "Project Related"). The *raw* string stored in
    each row's `question_type` field hasn't been independently confirmed to
    match exactly (could be "project_related" or similar). Run:
      print(sorted(set(q["question_type"] for q in questions)))
    first, and fix the keys below if they differ.
  - "Project Related" (-> graph / entity_relationship) has only ~40
    questions in the *entire* 500-question set -- short of this project's
    50-per-strategy target even before corpus-coverage filtering narrows it
    further. Flag this to the team: either accept fewer graph examples, or
    hand-write a small number of additional entity-relationship questions
    to cover just the shortfall (not the whole set).
"""

import json
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_META_PATH = DATA_DIR / "index" / "corpus_meta.jsonl"
EVAL_SET_PATH = DATA_DIR / "eval_set.jsonl"

# question_type -> (query_pattern, expected_strategy)
# Verify these keys against the dataset's actual question_type strings
# before trusting this mapping (see module docstring).
QUESTION_TYPE_MAPPING = {
    "basic": ("lookup", "vector"),
    "semantic": ("lookup", "vector"),
    "intra_document_reasoning": ("cross_document", "hybrid"),
    "constrained": ("cross_document", "hybrid"),
    "conflicting_info": ("cross_document", "hybrid"),
    "completeness": ("cross_document", "hybrid"),
    "miscellaneous": ("cross_document", "hybrid"),
    "project_related": ("entity_relationship", "graph"),
}

# Excluded entirely -- no ground-truth documents per the dataset's own docs.
EXCLUDED_QUESTION_TYPES = {
    "high_level",
    "info_not_found",
}

def load_local_doc_to_chunk_ids() -> dict[str, list[str]]:
    """Maps doc_id -> list of chunk_ids present in the LOCAL corpus subsample
    (not the full 500k-document benchmark). Requires corpus_meta.jsonl.
    """
    if not CORPUS_META_PATH.exists():
        raise FileNotFoundError(
            f"{CORPUS_META_PATH} not found. Run scripts/fetch_seed_data.py "
            "and scripts/build_corpus_index.py first -- this script needs "
            "to know which documents actually made it into the local "
            "subsample before it can filter questions against it."
        )

    doc_to_chunks: dict[str, list[str]] = defaultdict(list)
    with CORPUS_META_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            doc_id = chunk.get("doc_id")
            if doc_id:
                doc_to_chunks[doc_id].append(chunk["chunk_id"])
    return doc_to_chunks


def build_eval_set() -> None:
    print("Loading gold question set from onyx-dot-app/EnterpriseRAG-Bench...")
    questions = load_dataset("onyx-dot-app/EnterpriseRAG-Bench", "questions")["test"]

    doc_to_chunks = load_local_doc_to_chunk_ids()
    local_doc_ids = set(doc_to_chunks.keys())
    print(f"Local corpus subsample covers {len(local_doc_ids)} documents.")

    kept_by_strategy: dict[str, int] = defaultdict(int)
    skipped_excluded_or_unmapped = 0
    skipped_not_covered = 0

    rows = []
    for q in questions:
        q_type = q["question_type"]

        if q_type in EXCLUDED_QUESTION_TYPES or q_type not in QUESTION_TYPE_MAPPING:
            skipped_excluded_or_unmapped += 1
            continue

        expected_doc_ids = q["expected_doc_ids"]
        if not expected_doc_ids or not set(expected_doc_ids).issubset(local_doc_ids):
            skipped_not_covered += 1
            continue

        source_chunk_ids = [
            chunk_id for doc_id in expected_doc_ids for chunk_id in doc_to_chunks[doc_id]
        ]
        if not source_chunk_ids:
            skipped_not_covered += 1
            continue

        query_pattern, expected_strategy = QUESTION_TYPE_MAPPING[q_type]

        rows.append(
            {
                "question": q["question"],
                "expected_answer": q["gold_answer"],
                "expected_strategy": expected_strategy,
                "query_pattern": query_pattern,
                "source_chunk_ids": source_chunk_ids,
                # Extra fields for error analysis / debugging -- harmless,
                # build_eval_set.py only checks for the presence of its
                # required fields, not for an exact key set.
                "question_id": q["question_id"],
                "question_type": q_type,
            }
        )
        kept_by_strategy[expected_strategy] += 1

    EVAL_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVAL_SET_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    print(f"\nWrote {len(rows)} examples to {EVAL_SET_PATH}")
    print(f"By strategy: {dict(kept_by_strategy)}")
    print(f"Skipped (excluded/unmapped category): {skipped_excluded_or_unmapped}")
    print(f"Skipped (gold docs not fully covered by local subsample): {skipped_not_covered}")

    for strategy in ("vector", "hybrid", "graph"):
        count = kept_by_strategy.get(strategy, 0)
        if count < 50:
            print(f"WARNING: only {count} examples for strategy={strategy!r} (target: >=50)")


if __name__ == "__main__":
    build_eval_set()