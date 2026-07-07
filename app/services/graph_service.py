"""NL -> Cypher intent classification + GraphRAG hybrid retrieval (M9).

Used when queries require reasoning over relationships between entities.
Per the risk mitigation plan, this is the stretch-goal path: build vector +
hybrid first, add this once the core system is stable.
"""

from app.services.vector_service import RetrievedChunk


class GraphService:
    name = "graph"

    def __init__(self, graph_driver=None, nl_to_cypher=None):
        self.graph_driver = graph_driver
        self.nl_to_cypher = nl_to_cypher

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if self.graph_driver is None or self.nl_to_cypher is None:
            return []

        cypher_query = await self.nl_to_cypher.translate(query)
        records = await self.graph_driver.run(cypher_query)
        return [
            RetrievedChunk(
                chunk_id=record["id"],
                text=record["text"],
                score=record.get("score", 1.0),
                source="graph",
            )
            for record in records[:top_k]
        ]
