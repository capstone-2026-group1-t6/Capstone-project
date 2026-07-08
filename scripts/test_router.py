"""Quick manual smoke test for RouterService + RuleBasedClassifier.

Run from the repo root:
    python scripts/test_router.py
"""

import asyncio

from app.services.query_classifier import RuleBasedClassifier
from app.services.router_service import RouterService

TEST_QUERIES = [
    "Who reports to the engineering lead?",
    "Compare Q1 and Q2 sales performance",
    "What is the deadline for the API spec?",
]


async def main():
    classifier = RuleBasedClassifier()
    router = RouterService(classifier=classifier)

    for query in TEST_QUERIES:
        decision = await router.route(query)
        print(f"{query!r:55} -> {decision.strategy.value:8} (confidence={decision.confidence:.2f}, fell_back={decision.fell_back})")


if __name__ == "__main__":
    asyncio.run(main())