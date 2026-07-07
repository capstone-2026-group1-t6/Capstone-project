"""Prometheus metrics + logging for the classify -> retrieve -> generate pipeline.

Module 11 component: FastAPI microservices with Prometheus-based observability.
Default HTTP metrics (request count/latency) come from
prometheus-fastapi-instrumentator, wired up in app/main.py. This module adds
pipeline-specific custom metrics so we can see, per retrieval strategy:
  - how often each strategy is chosen
  - end-to-end latency per strategy (for Success Criterion 2)
  - router confidence (to tune the fallback threshold, Risk 1 mitigation)
"""

import logging

from prometheus_client import Counter, Histogram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("rag_platform")

RETRIEVAL_STRATEGY_SELECTED = Counter(
    "rag_retrieval_strategy_selected_total",
    "Number of queries routed to each retrieval strategy",
    ["strategy"],
)

RETRIEVAL_ROUTER_CONFIDENCE = Histogram(
    "rag_router_confidence",
    "Router confidence score for the selected strategy",
    ["strategy"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

QUERY_END_TO_END_LATENCY = Histogram(
    "rag_query_latency_seconds",
    "End-to-end query latency (classify + retrieve + generate)",
    ["strategy"],
    buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 13),
)

GENERATION_GROUNDING_FLAG = Counter(
    "rag_generation_grounded_total",
    "Count of generated answers, split by whether they were judged grounded",
    ["grounded"],
)
