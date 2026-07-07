import pytest

from app.services.router_service import RouterService, Strategy


class FakeClassifier:
    def __init__(self, strategy: str, confidence: float):
        self.strategy = strategy
        self.confidence = confidence

    async def predict(self, query: str):
        return self.strategy, self.confidence


@pytest.mark.asyncio
async def test_no_classifier_falls_back_to_hybrid():
    service = RouterService(classifier=None)
    decision = await service.route("any query")
    assert decision.strategy == Strategy.HYBRID
    assert decision.fell_back is True


@pytest.mark.asyncio
async def test_low_confidence_falls_back_to_hybrid():
    service = RouterService(classifier=FakeClassifier("graph", confidence=0.3))
    decision = await service.route("who reports to whom?")
    assert decision.strategy == Strategy.HYBRID
    assert decision.fell_back is True


@pytest.mark.asyncio
async def test_high_confidence_uses_predicted_strategy():
    service = RouterService(classifier=FakeClassifier("graph", confidence=0.9))
    decision = await service.route("who reports to whom?")
    assert decision.strategy == Strategy.GRAPH
    assert decision.fell_back is False


@pytest.mark.asyncio
async def test_forced_strategy_bypasses_router():
    service = RouterService(classifier=FakeClassifier("graph", confidence=0.9))
    decision = await service.route("anything", forced_strategy=Strategy.VECTOR)
    assert decision.strategy == Strategy.VECTOR
    assert decision.confidence == 1.0
    assert decision.fell_back is False
