import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.vector_service import RetrievedChunk


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(chunk_id="c1", text="The RAG router falls back to hybrid on low confidence.", score=0.92, source="docs/router.md"),
        RetrievedChunk(chunk_id="c2", text="Hybrid search merges vector and keyword hits before reranking.", score=0.81, source="docs/hybrid.md"),
    ]
