"""Grounded answer generation with citations.

Takes retrieved chunks (from vector/hybrid/graph) and produces a
citation-backed answer. Kept provider-agnostic behind `llm_client` so the
team can swap in whichever API is used for generation (see risk mitigation:
external API fallback if local inference is too slow).
"""

from dataclasses import dataclass

from app.services.vector_service import RetrievedChunk


@dataclass
class GeneratedAnswer:
    answer: str
    citations: list[str]
    strategy_used: str


class GenerateService:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def generate(
        self, query: str, messages: list[dict], chunks: list[RetrievedChunk], strategy_used: str
    ) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(
                answer="No relevant context was found for this query.",
                citations=[],
                strategy_used=strategy_used,
            )

        if self.llm_client is None:
            # Deterministic stub so tests/CI don't depend on a live LLM call.
            preview = chunks[0].text[:200]
            return GeneratedAnswer(
                answer=f"[stub answer grounded in {chunks[0].source}]: {preview}",
                citations=[c.chunk_id for c in chunks],
                strategy_used=strategy_used,
            )

        context = "\n\n".join(f"[{c.chunk_id}] {c.text}" for c in chunks)
        response_text = await self.llm_client.complete(query=query, messages=messages, context=context)
        return GeneratedAnswer(
            answer=response_text,
            citations=[c.chunk_id for c in chunks],
            strategy_used=strategy_used,
        )
