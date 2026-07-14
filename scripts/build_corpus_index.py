"""Builds the FAISS vector index + BM25 keyword index from data/seed/corpus.jsonl.

Run after scripts/fetch_seed_data.py. Embeds every chunk with
sentence-transformers/all-MiniLM-L6-v2 and persists a flat cosine-similarity
index + BM25 index + aligned metadata to data/index/, which
app.services.corpus_index.CorpusIndex.load() and KeywordIndex.load() read at API startup.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.services.corpus_index import CorpusIndex, KeywordIndex  # noqa: E402

SEED_CORPUS_PATH = REPO_ROOT / "data" / "seed" / "corpus.jsonl"


def main() -> None:
    if not SEED_CORPUS_PATH.exists():
        raise FileNotFoundError(f"{SEED_CORPUS_PATH} not found -- run scripts/fetch_seed_data.py first.")

    chunks = [json.loads(line) for line in SEED_CORPUS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Building indexes for {len(chunks)} chunks...")

    # Build and save vector index first (owns metadata file)
    vector_index = CorpusIndex.build(chunks)
    vector_index.save()
    print("Saved vector index to data/index/")

    # Build and save BM25 keyword index
    keyword_index = KeywordIndex.build(chunks)
    keyword_index.save()
    print("Saved BM25 keyword index to data/index/")

    print(f"Done! Built both indexes for {len(chunks)} chunks!")


if __name__ == "__main__":
    main()
