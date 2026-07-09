"""Hybrid (vector + keyword) search with cross-encoder re-ranking (M8).

Default retrieval path for unstructured document collections, and the
fallback target when the router's confidence is low (Risk 1 mitigation).
"""

import logging

from app.core.schemas import RetrievedChunk
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class HybridService:
    name = "hybrid"

    def __init__(self, corpus_index=None, keyword_index=None, reranker=None):
        self.vector_service = VectorService(corpus_index)
        self.keyword_index = keyword_index
        self.reranker = reranker

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not query or not query.strip():
            return []

        vector_hits = await self.vector_service.retrieve(query, top_k=top_k * 2)

        keyword_hits: list[RetrievedChunk] = []
        if self.keyword_index is not None:
            try:
                keyword_hits = await self.keyword_index.search(query, top_k=top_k * 2)
            except Exception:
                logger.exception("Keyword search failed for query=%r; continuing with vector hits only", query)

        candidates = self._merge_candidates(vector_hits, keyword_hits)

        if self.reranker is not None and candidates:
            try:
                candidates = await self.reranker.rerank(query, candidates)
            except Exception:
                logger.exception("Reranking failed for query=%r; falling back to merged (unreranked) order", query)

        results = candidates[:top_k]
        for chunk in results:
            chunk.strategy = "hybrid"

        return results

    @staticmethod
    def _merge_candidates(
        vector_hits: list[RetrievedChunk], keyword_hits: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        merged: dict[str, RetrievedChunk] = {}
        for hit in [*vector_hits, *keyword_hits]:
            existing = merged.get(hit.chunk_id)
            if existing is None or hit.score > existing.score:
                merged[hit.chunk_id] = hit
        return sorted(merged.values(), key=lambda c: c.score, reverse=True)