"""Neo4j-backed graph driver for GraphService (M9).

Thin async wrapper around the official `neo4j` driver, exposing the single
`.run(cypher, parameters) -> list[dict]` method GraphService depends on. The
driver's session.run is synchronous, so it's executed in a thread via
asyncio.to_thread -- same pattern as CorpusIndex/KeywordIndex
(app/services/corpus_index.py).
"""

import asyncio

from neo4j import GraphDatabase

from app.core.config import settings


class Neo4jGraphDriver:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        self.database = database or settings.graph_db_database
        self._driver = GraphDatabase.driver(
            uri or settings.graph_db_uri,
            auth=(user or settings.graph_db_user, password or settings.graph_db_password),
        )

    def close(self) -> None:
        self._driver.close()

    async def run(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        return await asyncio.to_thread(self._run_sync, cypher, parameters or {})

    def _run_sync(self, cypher: str, parameters: dict) -> list[dict]:
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, parameters)
            return [record.data() for record in result]
