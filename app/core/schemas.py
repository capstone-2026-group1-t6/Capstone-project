"""Shared data contracts used across all retrieval strategies.

IMPORTANT: RetrievedChunk lives HERE (not inside vector_service.py) so that
VectorService, HybridService, and GraphService all return the exact same
type. RouterService depends on this — it treats the three services
interchangeably, so their outputs must be structurally identical.


"""

from dataclasses import dataclass, field
from typing import Literal

RetrievalStrategy = Literal["vector", "hybrid", "graph"]


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    source: str
    # Which strategy produced this chunk — useful for the router-accuracy
    # metric in the evaluation plan (§ "router accuracy ≥ 80%").
    strategy: RetrievalStrategy = "vector"
    metadata: dict = field(default_factory=dict)