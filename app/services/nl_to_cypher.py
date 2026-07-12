"""Rule-based NL -> Cypher translation for GraphService (M9).

Same philosophy as RuleBasedClassifier (app/services/query_classifier.py):
deterministic regex extraction over a small, fixed graph schema, so
GraphRAG is buildable and testable before any LLM-backed NL->Cypher
component exists. Swappable later behind the same
`.translate(query) -> CypherQuery | None` interface -- GraphService only
depends on that shape, not on how the query was produced.

Graph schema this assumes (seeded by scripts/build_graph_index.py):
    (:Person {name})-[:REPORTS_TO]->(:Person)
    (:Person {name})-[:WORKS_ON]->(:Project {name})
    (:Person {name})-[:OWNS]->(:Project {name})
    (:Person {name})-[:COLLABORATES_WITH]-(:Person)

Every template returns rows already shaped like RetrievedChunk fields
(text/id/score/source) so GraphService can build chunks directly from
records without a separate per-intent formatting step.
"""

import re
from dataclasses import dataclass, field
from app.services.llm_client import LLMClient


@dataclass
class CypherQuery:
    text: str
    parameters: dict = field(default_factory=dict)


class NLToCypher:
    """Dynamic NL -> Cypher translator using LLM.
    """
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def translate(self, query: str) -> CypherQuery | None:
        cypher_text = await self.llm_client.generate_cypher(query)
        if cypher_text:
            return CypherQuery(text=cypher_text, parameters={})
        return None
