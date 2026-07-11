"""Downloads and pre-processes the public seed dataset(s) into data/seed/.

Per the proposal's data-source plan: MIT/public-domain seed datasets only,
~1,000-5,000 chunks each. No proprietary data, no scraped data, no paid APIs.

Dataset: onyx-dot-app/EnterpriseRAG-Bench ("documents" config, "test" split)
on Hugging Face. Chosen because it ships a real multi-source document corpus
(Slack, Gmail, Linear, Google Drive, HubSpot, Fireflies, GitHub, Jira,
Confluence) with genuine entity/relationship structure between people,
tickets, and docs -- needed to exercise the router's `graph` strategy, which
a plain Wikipedia-style QA corpus wouldn't give us.
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
MAX_CHUNKS_PER_SOURCE = 600  # spreads the budget across source_types instead
# of letting one large source (e.g. Slack) crowd out the others
CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 100


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


def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading {DATASET_URL} ({DATASET_CONFIG}/{DATASET_SPLIT})...")
    documents = load_dataset(DATASET_URL, DATASET_CONFIG, split=DATASET_SPLIT, streaming=True)
    documents = documents.shuffle(seed=42, buffer_size=10_000)

    rows = []
    per_source_count: dict[str, int] = defaultdict(int)

    for doc in documents:
        if len(rows) >= MAX_CHUNKS:
            break

        source_type = doc["source_type"]
        if per_source_count[source_type] >= MAX_CHUNKS_PER_SOURCE:
            continue

        for i, chunk in enumerate(chunk_text(doc["content"])):
            if len(rows) >= MAX_CHUNKS or per_source_count[source_type] >= MAX_CHUNKS_PER_SOURCE:
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

    out_path = SEED_DIR / "corpus.jsonl"
    out_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    license_path = SEED_DIR / "LICENSE.txt"
    license_path.write_text(
        f"Source: https://huggingface.co/datasets/{DATASET_URL}\nLicense: {DATASET_LICENSE}\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(rows)} chunks from {len(per_source_count)} source types to {out_path}")
    print(f"Per-source counts: {dict(per_source_count)}")


if __name__ == "__main__":
    main()
