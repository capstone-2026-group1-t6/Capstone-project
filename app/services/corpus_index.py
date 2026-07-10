"""Embedding-backed vector index over the seed corpus.

Builds/loads a flat cosine-similarity FAISS index and exposes the async
`.search(query, top_k)` interface VectorService/HybridService already depend
on (see app/services/vector_service.py). The corpus is capped at a few
thousand chunks (scripts/fetch_seed_data.py), so an exact flat index is fast
enough -- no need for an approximate index or a hosted vector DB.

Build the index with `python scripts/build_corpus_index.py` after running
scripts/fetch_seed_data.py.
"""

import asyncio
import json
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

from app.core.schemas import RetrievedChunk

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_INDEX_PATH = DATA_DIR / "index" / "corpus.faiss"
DEFAULT_META_PATH = DATA_DIR / "index" / "corpus_meta.jsonl"


class CorpusIndex:
    """Flat cosine-similarity FAISS index, paired with the embedder used to
    embed both the corpus and incoming queries (must match, or scores are
    meaningless).
    """

    def __init__(self, index: faiss.Index, metadata: list[dict], model: SentenceTransformer):
        self._index = index
        self._metadata = metadata
        self._model = model

    @classmethod
    def build(cls, chunks: list[dict], model_name: str = EMBEDDING_MODEL_NAME) -> "CorpusIndex":
        model = SentenceTransformer(model_name)
        embeddings = model.encode(
            [c["text"] for c in chunks],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).astype("float32")

        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        return cls(index, chunks, model)

    @classmethod
    def load(
        cls,
        index_path: Path = DEFAULT_INDEX_PATH,
        meta_path: Path = DEFAULT_META_PATH,
        model_name: str = EMBEDDING_MODEL_NAME,
    ) -> "CorpusIndex":
        index = faiss.read_index(str(index_path))
        metadata = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        model = SentenceTransformer(model_name)
        return cls(index, metadata, model)

    def save(self, index_path: Path = DEFAULT_INDEX_PATH, meta_path: Path = DEFAULT_META_PATH) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_path))
        meta_path.write_text("\n".join(json.dumps(c) for c in self._metadata), encoding="utf-8")

    async def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        return await asyncio.to_thread(self._search_sync, query, top_k)

    def _search_sync(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if self._index.ntotal == 0:
            return []

        query_embedding = self._model.encode(
            [query], convert_to_numpy=True, normalize_embeddings=True
        ).astype("float32")
        scores, indices = self._index.search(query_embedding, min(top_k, self._index.ntotal))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = self._metadata[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    text=chunk["text"],
                    score=float(score),
                    source=chunk["source"],
                    strategy="vector",
                    metadata={"doc_id": chunk.get("doc_id", ""), "title": chunk.get("title", "")},
                )
            )
        return results
