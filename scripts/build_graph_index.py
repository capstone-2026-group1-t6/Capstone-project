"""Seeds Neo4j from data/seed/graph_seed.json.

Run against a live Neo4j instance (see RAGPLATFORM_GRAPH_DB_* in
.env.example / docker-compose.yml's neo4j service) to populate the org
chart NLToCypher's templates query against (app/services/nl_to_cypher.py).
Idempotent: uses MERGE throughout, so re-running it is safe.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.services.graph_driver import Neo4jGraphDriver  # noqa: E402

SEED_GRAPH_PATH = REPO_ROOT / "data" / "seed" / "graph_seed.json"


async def main() -> None:
    if not SEED_GRAPH_PATH.exists():
        raise FileNotFoundError(f"{SEED_GRAPH_PATH} not found.")

    seed = json.loads(SEED_GRAPH_PATH.read_text(encoding="utf-8"))
    driver = Neo4jGraphDriver()

    try:
        for person in seed.get("people", []):
            await driver.run(
                "MERGE (p:Person {name: $name}) SET p.title = $title",
                {"name": person["name"], "title": person.get("title", "")},
            )
        for project in seed.get("projects", []):
            await driver.run("MERGE (proj:Project {name: $name})", {"name": project["name"]})
        for rel in seed.get("reports_to", []):
            await driver.run(
                "MATCH (p:Person {name: $person}), (m:Person {name: $manager}) "
                "MERGE (p)-[:REPORTS_TO]->(m)",
                {"person": rel["person"], "manager": rel["manager"]},
            )
        for rel in seed.get("owns", []):
            await driver.run(
                "MATCH (p:Person {name: $person}), (proj:Project {name: $project}) "
                "MERGE (p)-[:OWNS]->(proj)",
                {"person": rel["person"], "project": rel["project"]},
            )
        for rel in seed.get("works_on", []):
            await driver.run(
                "MATCH (p:Person {name: $person}), (proj:Project {name: $project}) "
                "MERGE (p)-[:WORKS_ON]->(proj)",
                {"person": rel["person"], "project": rel["project"]},
            )
        for rel in seed.get("collaborates_with", []):
            await driver.run(
                "MATCH (a:Person {name: $a}), (b:Person {name: $b}) "
                "MERGE (a)-[:COLLABORATES_WITH]-(b)",
                {"a": rel["person_a"], "b": rel["person_b"]},
            )
    finally:
        driver.close()

    print(
        f"Seeded {len(seed.get('people', []))} people and "
        f"{len(seed.get('projects', []))} projects into Neo4j."
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
