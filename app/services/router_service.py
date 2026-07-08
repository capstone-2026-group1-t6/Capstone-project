"""Strategy-selection router: picks vector / hybrid / graph per query.

Success Criterion 3: correct mode chosen for >= 80% of held-out queries.
Risk 1 mitigation: when confidence is below the configured threshold, fall
back to hybrid rather than guessing, and callers may pass `forced_strategy`
to bypass the router entirely (manual override).
"""

import logging
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.observability import RETRIEVAL_ROUTER_CONFIDENCE, RETRIEVAL_STRATEGY_SELECTED

logger = logging.getLogger(__name__)


class Strategy(str, Enum):
    VECTOR = "vector"
    HYBRID = "hybrid"
    GRAPH = "graph"


@dataclass
class RoutingDecision:
    strategy: Strategy
    confidence: float
    fell_back: bool


class RouterService:
    """Picks a retrieval strategy for a query.

    `classifier` is anything with an async .predict(query) -> (str, float)
    method — RuleBasedClassifier (app/services/query_classifier.py) for now,
    swappable later for a fine-tuned model without touching this class or
    app/routers/query.py.
    """

    def __init__(self, classifier=None):
        self.classifier = classifier

    async def route(self, query: str, forced_strategy: Strategy | None = None) -> RoutingDecision:
        if forced_strategy is not None:
            return RoutingDecision(strategy=forced_strategy, confidence=1.0, fell_back=False)

        if not query or not query.strip():
            logger.warning("RouterService.route called with an empty query; defaulting to hybrid")
            decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=0.0, fell_back=True)

        elif self.classifier is None:
            logger.warning("RouterService.route called with no classifier configured; defaulting to hybrid")
            decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=0.0, fell_back=True)

        else:
            try:
                predicted_strategy, confidence = await self.classifier.predict(query)
                strategy = Strategy(predicted_strategy)
            except ValueError:
                # classifier returned a string that isn't "vector"/"hybrid"/"graph"
                logger.exception("Classifier returned an invalid strategy for query=%r", query)
                decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=0.0, fell_back=True)
            except Exception:
                logger.exception("Classifier prediction failed for query=%r", query)
                decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=0.0, fell_back=True)
            else:
                if confidence < settings.router_confidence_threshold:
                    decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=confidence, fell_back=True)
                else:
                    decision = RoutingDecision(strategy=strategy, confidence=confidence, fell_back=False)

        RETRIEVAL_STRATEGY_SELECTED.labels(strategy=decision.strategy.value).inc()
        RETRIEVAL_ROUTER_CONFIDENCE.labels(strategy=decision.strategy.value).observe(decision.confidence)
        return decision