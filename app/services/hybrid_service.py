"""Hybrid (vector + keyword) search with cross-encoder re-ranking (M8).

Default retrieval path for unstructured document collections, and the
fallback target when the router's confidence is low (Risk 1 mitigation).
"""

from app.services.vector_service import RetrievedChunk, VectorService


class HybridService:
    name = "hybrid"

    def __init__(self, corpus_index=None, keyword_index=None, reranker=None):
        self.vector_service = VectorService(corpus_index)
        self.keyword_index = keyword_index
        self.reranker = reranker

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        vector_hits = await self.vector_service.retrieve(query, top_k=top_k * 2)
        keyword_hits = (
            await self.keyword_index.search(query, top_k=top_k * 2)
            if self.keyword_index
            else []
        )
        candidates = self._merge_candidates(vector_hits, keyword_hits)

        if self.reranker is not None and candidates:
            candidates = await self.reranker.rerank(query, candidates)

        return candidates[:top_k]

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
