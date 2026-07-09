"""Vector-only retrieval — the baseline path (M8 reference implementation).

This service performs semantic vector search over the indexed corpus.
It is the baseline retrieval strategy used for comparison against
Hybrid Search and GraphRAG during evaluation.
"""

import logging

from app.core.config import settings
from app.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class VectorService:
    """Vector-only retrieval service."""

    name = "vector"

    def __init__(self, corpus_index=None):
        self.corpus_index = corpus_index

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the top-k most relevant chunks using vector similarity.

        Args:
            query: User query.
            top_k: Number of chunks to retrieve. Uses the configured default
                   if not provided.

        Returns:
            List of RetrievedChunk objects ordered by similarity score.
        """

        if not query or not query.strip():
            return []

        if self.corpus_index is None:
            logger.error("VectorService.retrieve called with no corpus_index configured")
            return []

        top_k = top_k or settings.default_top_k

        try:
            results = await self.corpus_index.search(
                query=query,
                top_k=top_k,
            )
            return results or []
        except Exception:
            logger.exception("Vector search failed for query=%r", query)
            return []
        
        
        