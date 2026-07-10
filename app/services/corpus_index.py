"""Embedding-backed vector index + BM25 keyword index over the seed corpus.

Builds/loads a flat cosine-similarity FAISS index (CorpusIndex) and a BM25
keyword index (KeywordIndex), both exposing the async `.search(query, top_k)`
interface VectorService/HybridService already depend on (see
app/services/vector_service.py and app/services/hybrid_service.py). Both
indexes are built over the exact same chunks and share the same metadata,
so results from either can be merged by `chunk_id` in HybridService.

The corpus is capped at a few thousand chunks (scripts/fetch_seed_data.py),
so an exact flat FAISS index and an in-memory BM25 index are both fast
enough -- no need for an approximate index, a hosted vector DB, or
Elasticsearch.

Build both indexes with `python scripts/build_corpus_index.py` after running
scripts/fetch_seed_data.py. That script should call
`corpus_index.save()` BEFORE `keyword_index.save()` -- CorpusIndex owns
writing the shared metadata file; KeywordIndex only writes it if it's
missing, to avoid the two classes racing to write the same file.
"""

import asyncio
import json
import pickle
import re
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.core.schemas import RetrievedChunk

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_INDEX_PATH = DATA_DIR / "index" / "corpus.faiss"
DEFAULT_META_PATH = DATA_DIR / "index" / "corpus_meta.jsonl"
DEFAULT_BM25_PATH = DATA_DIR / "index" / "corpus_bm25.pkl"

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric-only tokenizer shared by build time and query
    time. Must stay identical in both places, or BM25 scores become
    meaningless (a query tokenized differently than the corpus won't match
    terms it should).
    """
    return _TOKEN_PATTERN.findall(text.lower())


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


class KeywordIndex:
    """BM25 keyword index, built over the exact same chunks as CorpusIndex
    and sharing its metadata file. HybridService merges hits from both by
    `chunk_id`, so field names (chunk_id/source/doc_id/title) must match
    CorpusIndex's exactly -- they do, since both read the same metadata.
    """

    def __init__(self, bm25: BM25Okapi, metadata: list[dict]):
        self._bm25 = bm25
        self._metadata = metadata

    @classmethod
    def build(cls, chunks: list[dict]) -> "KeywordIndex":
        tokenized_corpus = [_tokenize(c["text"]) for c in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        return cls(bm25, chunks)

    @classmethod
    def load(
        cls,
        bm25_path: Path = DEFAULT_BM25_PATH,
        meta_path: Path = DEFAULT_META_PATH,
    ) -> "KeywordIndex":
        with bm25_path.open("rb") as f:
            bm25 = pickle.load(f)
        metadata = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return cls(bm25, metadata)

    def save(self, bm25_path: Path = DEFAULT_BM25_PATH, meta_path: Path = DEFAULT_META_PATH) -> None:
        bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with bm25_path.open("wb") as f:
            pickle.dump(self._bm25, f)
        # meta_path is owned/written by CorpusIndex.save(); only write it
        # here if it's missing, so the two indexes never race to overwrite
        # each other's copy of the (identical) metadata.
        if not meta_path.exists():
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text("\n".join(json.dumps(c) for c in self._metadata), encoding="utf-8")

    async def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        return await asyncio.to_thread(self._search_sync, query, top_k)

    def _search_sync(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self._metadata:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = np.asarray(self._bm25.get_scores(query_tokens))
        k = min(top_k, len(self._metadata))

        top_indices = np.argpartition(-scores, k - 1)[:k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                # No real lexical overlap with the query -- don't pad the
                # result list with irrelevant chunks just to hit top_k.
                continue
            chunk = self._metadata[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    text=chunk["text"],
                    score=score,
                    source=chunk["source"],
                    strategy="hybrid",
                    metadata={"doc_id": chunk.get("doc_id", ""), "title": chunk.get("title", "")},
                )
            )
        return results