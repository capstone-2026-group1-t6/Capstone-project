"""Builds the FAISS vector index from data/seed/corpus.jsonl.

Run after scripts/fetch_seed_data.py. Embeds every chunk with
sentence-transformers/all-MiniLM-L6-v2 and persists a flat cosine-similarity
index + aligned metadata to data/index/, which
app.services.corpus_index.CorpusIndex.load() reads at API startup.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.services.corpus_index import CorpusIndex  # noqa: E402

SEED_CORPUS_PATH = REPO_ROOT / "data" / "seed" / "corpus.jsonl"


def main() -> None:
    if not SEED_CORPUS_PATH.exists():
        raise FileNotFoundError(f"{SEED_CORPUS_PATH} not found -- run scripts/fetch_seed_data.py first.")

    chunks = [json.loads(line) for line in SEED_CORPUS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Embedding {len(chunks)} chunks with {CorpusIndex.__module__}...")

    index = CorpusIndex.build(chunks)
    index.save()
    print(f"Saved index with {len(chunks)} vectors to data/index/")


if __name__ == "__main__":
    main()
