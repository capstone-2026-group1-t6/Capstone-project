"""Strategy-selection router: picks vector / hybrid / graph per query.

Success Criterion 3: correct mode chosen for >= 80% of held-out queries.
Risk 1 mitigation: when confidence is below the configured threshold, fall
back to hybrid rather than guessing, and callers may pass `forced_strategy`
to bypass the router entirely (manual override).
"""

from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.observability import RETRIEVAL_ROUTER_CONFIDENCE, RETRIEVAL_STRATEGY_SELECTED


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
    """Classifier stub: query pattern -> {vector, hybrid, graph}.

    The real classifier (rule-based first pass, upgradeable to a small
    fine-tuned model) is Hosam/Yusra's sprint deliverable. This class defines
    the contract every caller and test depends on, so it can be swapped in
    without touching app/routers/query.py.
    """

    def __init__(self, classifier=None):
        self.classifier = classifier

    async def route(self, query: str, forced_strategy: Strategy | None = None) -> RoutingDecision:
        if forced_strategy is not None:
            return RoutingDecision(strategy=forced_strategy, confidence=1.0, fell_back=False)

        if self.classifier is None:
            decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=0.0, fell_back=True)
        else:
            predicted_strategy, confidence = await self.classifier.predict(query)
            if confidence < settings.router_confidence_threshold:
                decision = RoutingDecision(strategy=Strategy.HYBRID, confidence=confidence, fell_back=True)
            else:
                decision = RoutingDecision(strategy=Strategy(predicted_strategy), confidence=confidence, fell_back=False)

        RETRIEVAL_STRATEGY_SELECTED.labels(strategy=decision.strategy.value).inc()
        RETRIEVAL_ROUTER_CONFIDENCE.labels(strategy=decision.strategy.value).observe(decision.confidence)
        return decision
