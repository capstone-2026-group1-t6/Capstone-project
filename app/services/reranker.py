"""Cross-encoder re-ranker used by HybridService.

Sprint version: loads a pretrained cross-encoder as-is (no training).
Component 5 (Module 7) later fine-tunes this same model on our corpus —
when that lands, only `settings.cross_encoder_model` (app/core/config.py)
changes; HybridService and everything calling it stays untouched.
"""

import asyncio
import logging

from app.core.config import settings
from app.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Wraps sentence-transformers' CrossEncoder with the async interface
    HybridService expects: `await reranker.rerank(query, candidates)`.

    The underlying library call is synchronous (and CPU/GPU-bound), so it's
    run in a thread via asyncio.to_thread to avoid blocking the event loop.
    """

    def __init__(self, model_name: str | None = None):
        # Imported lazily so importing this module doesn't require
        # sentence-transformers to be installed unless a reranker is
        # actually constructed (keeps VectorService-only tests light).
        from sentence_transformers import CrossEncoder

        self.model_name = model_name or settings.cross_encoder_model
        self._model = CrossEncoder(self.model_name)

    async def rerank(
        self, query: str, candidates: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        pairs = [(query, chunk.text) for chunk in candidates]

        try:
            scores = await asyncio.to_thread(self._model.predict, pairs)
        except Exception:
            logger.exception(
                "Cross-encoder reranking failed for query=%r; returning candidates in original order", query
            )
            return candidates

        for chunk, score in zip(candidates, scores):
            chunk.score = float(score)

        return sorted(candidates, key=lambda c: c.score, reverse=True)