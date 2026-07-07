"""Vector-only retrieval — the baseline path (M8 reference implementation).

This is intentionally the simplest strategy: embed the query, cosine-similarity
search against the corpus embeddings, return top_k chunks. It is also the
project's baseline for comparison in the evaluation plan.
"""

from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    source: str


class VectorService:
    """Stub interface — implementation lands during the sprint (Yusra: data,
    Hosam: baseline implementation). Kept here so the API contract and tests
    can be written now and wired up as the real embedding index comes online.
    """

    name = "vector"

    def __init__(self, corpus_index=None):
        self.corpus_index = corpus_index

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if self.corpus_index is None:
            return []
        return await self.corpus_index.search(query, top_k=top_k)
