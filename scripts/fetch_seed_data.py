"""Downloads and pre-processes the public seed dataset(s) into data/seed/.

Per the proposal's data-source plan: MIT/public-domain seed datasets only,
~1,000-5,000 chunks each. No proprietary data, no scraped data, no paid APIs.

Dataset: onyx-dot-app/EnterpriseRAG-Bench ("documents" config, "test" split)
on Hugging Face. Chosen because it ships a real multi-source document corpus
(Slack, Gmail, Linear, Google Drive, HubSpot, Fireflies, GitHub, Jira,
Confluence) with genuine entity/relationship structure between people,
tickets, and docs -- needed to exercise the router's `graph` strategy, which
a plain Wikipedia-style QA corpus wouldn't give us.

COVERAGE GUARANTEE: scripts/generate_eval_set_from_benchmark.py needs a set
of specific doc_ids to be present locally (the gold `expected_doc_ids` of
eval-eligible questions) or those questions get silently dropped. Pure
random sampling essentially never catches enough of them together (see
diagnose_required_docs.py). So this script first identifies that required
doc_id set directly from the questions split, guarantees every one of them
gets included (bypassing the normal per-source caps), and only then fills
the remaining chunk budget with random documents for source-type diversity.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings  # noqa: E402

SEED_DIR = REPO_ROOT / "data" / "seed"

DATASET_URL = "onyx-dot-app/EnterpriseRAG-Bench"
DATASET_LICENSE = "MIT"

DATASET_CONFIG = "documents"
DATASET_SPLIT = "test"

MAX_CHUNKS = settings.max_chunks_per_corpus
MAX_CHUNKS_PER_SOURCE = 600  # hard ceiling on chunks per source_type for the
# RANDOM FILL portion only -- required docs (see below) bypass this, since
# skipping a required doc just because its source_type is already "full"
# would silently break eval coverage again.
MAX_DOCS_PER_SOURCE = 150  # same bypass rule applies: only constrains the
# random-fill portion, not required docs.
MAX_CHUNKS_PER_DOC = 4  # caps chunks taken from any single document so a few
# long docs (Confluence/Fireflies, ~15-20 chunks each) can't alone exhaust
# MAX_CHUNKS. Applies to required docs too -- eval-set coverage only needs
# the doc_id present locally with at least one chunk, not every chunk of it
# (see generate_eval_set_from_benchmark.py: it only checks
# expected_doc_ids.issubset(local_doc_ids), not full-content coverage).
CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 100

# Must be kept in sync with scripts/generate_eval_set_from_benchmark.py --
# this determines which doc_ids that script will actually need.
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

EXCLUDED_QUESTION_TYPES = {
    "high_level",
    "info_not_found",
}


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]


def load_required_doc_ids() -> set[str]:
    """Doc_ids that eval-eligible questions need present locally, so we can
    guarantee their inclusion instead of hoping random sampling catches
    them. Mirrors the exact filtering generate_eval_set_from_benchmark.py
    applies (excluded categories + unmapped types), so this set matches
    what that script will actually look for.
    """
    print("Determining required doc_ids from the eval question set...")
    questions = load_dataset(DATASET_URL, "questions")["test"]

    required: set[str] = set()
    for q in questions:
        q_type = q["question_type"]
        if q_type in EXCLUDED_QUESTION_TYPES or q_type not in QUESTION_TYPE_MAPPING:
            continue
        expected_doc_ids = q["expected_doc_ids"]
        if expected_doc_ids:
            required.update(expected_doc_ids)

    print(f"  {len(required)} unique documents required for full eval coverage.")
    return required


def add_doc(
    doc,
    rows: list,
    per_source_count: dict,
    per_source_docs: dict,
    chunk_cap: int = MAX_CHUNKS_PER_DOC,
) -> bool:
    """Chunks a document and appends rows, updating counters in place.
    Returns True if at least one chunk was added.
    """
    source_type = doc["source_type"]
    doc_chunks = chunk_text(doc["content"])
    if not doc_chunks:
        return False

    added_any = False
    for i, chunk in enumerate(doc_chunks[:chunk_cap]):
        if len(rows) >= MAX_CHUNKS:
            break
        rows.append(
            {
                "chunk_id": f"{doc['doc_id']}-{i:04d}",
                "text": chunk,
                "source": source_type,
                "doc_id": doc["doc_id"],
                "title": doc["title"],
            }
        )
        per_source_count[source_type] += 1
        added_any = True

    if added_any:
        per_source_docs[source_type] += 1
    return added_any


def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)

    required_doc_ids = load_required_doc_ids()

    print(f"Loading {DATASET_URL} ({DATASET_CONFIG}/{DATASET_SPLIT})...")
    documents = load_dataset(DATASET_URL, DATASET_CONFIG, split=DATASET_SPLIT, streaming=True)
    documents = documents.shuffle(seed=42, buffer_size=10_000)

    rows: list = []
    per_source_count: dict[str, int] = defaultdict(int)
    per_source_docs: dict[str, int] = defaultdict(int)
    found_doc_ids: set[str] = set()
    required_found: set[str] = set()

    print("Building corpus (required docs guaranteed first, then random fill)...")
    for doc in documents:
        if len(rows) >= MAX_CHUNKS:
            break

        doc_id = doc["doc_id"]
        if doc_id in found_doc_ids:
            continue

        source_type = doc["source_type"]
        is_required = doc_id in required_doc_ids

        # Random-fill docs still respect the per-source caps. Required docs
        # bypass them entirely -- coverage must not depend on cap timing.
        if not is_required:
            if per_source_count[source_type] >= MAX_CHUNKS_PER_SOURCE:
                continue
            if per_source_docs[source_type] >= MAX_DOCS_PER_SOURCE:
                continue

        if add_doc(doc, rows, per_source_count, per_source_docs):
            found_doc_ids.add(doc_id)
            if is_required:
                required_found.add(doc_id)

    missing_required = required_doc_ids - required_found
    print(f"\nRequired-doc coverage: {len(required_found)}/{len(required_doc_ids)} found.")
    if missing_required:
        print(
            f"  WARNING: {len(missing_required)} required doc_ids were not found in the "
            f"'{DATASET_SPLIT}' split of '{DATASET_CONFIG}' (they may only exist in a "
            f"different split/config, or MAX_CHUNKS was reached before finding them)."
        )

    out_path = SEED_DIR / "corpus.jsonl"

    # Preserve any user-uploaded chunks (lines not from the seed dataset)
    seed_source_types = {"confluence", "fireflies", "slack", "gmail", "linear",
                         "google_drive", "hubspot", "github", "jira"}
    preserved_uploads: list[str] = []
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if obj.get("source", "") not in seed_source_types:
                    preserved_uploads.append(line)
            except json.JSONDecodeError:
                pass

    seed_lines = "\n".join(json.dumps(row) for row in rows)
    upload_lines = "\n" + "\n".join(preserved_uploads) if preserved_uploads else ""
    out_path.write_text(seed_lines + upload_lines, encoding="utf-8")

    license_path = SEED_DIR / "LICENSE.txt"
    license_path.write_text(
        f"Source: https://huggingface.co/datasets/{DATASET_URL}\nLicense: {DATASET_LICENSE}\n",
        encoding="utf-8",
    )

    print(f"\nWrote {len(rows)} chunks from {len(per_source_count)} source types to {out_path}")
    print(f"Per-source chunk counts: {dict(per_source_count)}")
    print(f"Per-source doc counts:   {dict(per_source_docs)}")
    print(f"Total unique documents: {sum(per_source_docs.values())}")


if __name__ == "__main__":
    main()