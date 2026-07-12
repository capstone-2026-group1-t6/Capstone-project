import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.observability import GENERATION_GROUNDING_FLAG, QUERY_END_TO_END_LATENCY, logger
from app.services.corpus_index import DEFAULT_INDEX_PATH, DEFAULT_META_PATH, CorpusIndex
from app.services.generate_service import GenerateService
from app.services.graph_driver import Neo4jGraphDriver
from app.services.graph_service import GraphService
from app.services.hybrid_service import HybridService
from app.services.nl_to_cypher import NLToCypher
from app.services.router_service import RouterService, Strategy
from app.services.vector_service import VectorService

router = APIRouter(prefix="/query", tags=["query"])


def _load_corpus_index() -> CorpusIndex | None:
    """Loads the built FAISS index if present (see scripts/build_corpus_index.py).
    Falls back to None -- vector/hybrid retrieval then returns no chunks
    instead of failing, same as before the index existed.
    """
    if not DEFAULT_INDEX_PATH.exists() or not DEFAULT_META_PATH.exists():
        logger.warning("No corpus index found at %s; retrieval will return no chunks.", DEFAULT_INDEX_PATH)
        return None
    return CorpusIndex.load()


def _load_graph_driver() -> Neo4jGraphDriver | None:
    """Connects to Neo4j if a graph DB is configured (password non-empty).
    Falls back to None -- graph retrieval then returns no chunks instead of
    failing, same degrade-gracefully pattern as _load_corpus_index above.
    """
    if not settings.graph_db_password:
        logger.warning("No graph database configured; GraphRAG retrieval will return no chunks.")
        return None
    try:
        return Neo4jGraphDriver()
    except Exception:
        logger.exception("Failed to connect to graph database; GraphRAG retrieval will return no chunks.")
        return None


_corpus_index = _load_corpus_index()
_graph_driver = _load_graph_driver()

_router_service = RouterService()
_vector_service = VectorService(corpus_index=_corpus_index)
_hybrid_service = HybridService(corpus_index=_corpus_index)
_graph_service = GraphService(
    graph_driver=_graph_driver,
    nl_to_cypher=NLToCypher() if _graph_driver is not None else None,
)
_generate_service = GenerateService()


def shutdown_graph_driver() -> None:
    if _graph_driver is not None:
        _graph_driver.close()

_STRATEGY_MAP = {
    Strategy.VECTOR: _vector_service,
    Strategy.HYBRID: _hybrid_service,
    Strategy.GRAPH: _graph_service,
}


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    forced_strategy: Strategy | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[str]
    strategy_used: str
    router_confidence: float
    fell_back_to_hybrid: bool
    latency_seconds: float


@router.post("", response_model=QueryResponse)
async def run_query(request: QueryRequest) -> QueryResponse:
    start = time.perf_counter()

    decision = await _router_service.route(request.query, forced_strategy=request.forced_strategy)
    retriever = _STRATEGY_MAP[decision.strategy]
    chunks = await retriever.retrieve(request.query, top_k=request.top_k)
    result = await _generate_service.generate(request.query, chunks, decision.strategy.value)

    latency = time.perf_counter() - start
    QUERY_END_TO_END_LATENCY.labels(strategy=decision.strategy.value).observe(latency)
    GENERATION_GROUNDING_FLAG.labels(grounded=str(bool(result.citations))).inc()

    logger.info(
        "query served",
        extra={
            "strategy": decision.strategy.value,
            "fell_back": decision.fell_back,
            "latency_seconds": round(latency, 3),
        },
    )

    return QueryResponse(
        answer=result.answer,
        citations=result.citations,
        strategy_used=result.strategy_used,
        router_confidence=decision.confidence,
        fell_back_to_hybrid=decision.fell_back,
        latency_seconds=latency,
    )
