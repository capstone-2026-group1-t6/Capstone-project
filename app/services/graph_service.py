"""NL -> Cypher intent classification + GraphRAG hybrid retrieval (M9).

Used when queries require reasoning over relationships between entities.
Per the risk mitigation plan, this is the stretch-goal path: build vector +
hybrid first, add this once the core system is stable.
"""

import logging

from app.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class GraphService:
    name = "graph"

    def __init__(self, graph_driver=None, nl_to_cypher=None):
        self.graph_driver = graph_driver
        self.nl_to_cypher = nl_to_cypher

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not query or not query.strip():
            return []

        if self.graph_driver is None or self.nl_to_cypher is None:
            return []

        try:
            cypher_query = await self.nl_to_cypher.translate(query)
        except Exception:
            logger.exception("NL->Cypher translation failed for query=%r", query)
            return []

        if cypher_query is None:
            logger.info("NL->Cypher found no matching intent for query=%r", query)
            return []

        try:
            records = await self.graph_driver.run(cypher_query.text, cypher_query.parameters)
        except Exception:
            logger.exception("Graph query execution failed for query=%r", query)
            return []

        return [
            RetrievedChunk(
                chunk_id=record["id"],
                text=record["text"],
                score=record.get("score", 1.0),
                source=record.get("source", "graph"),
                strategy="graph",
            )
            for record in records[:top_k]
        ]