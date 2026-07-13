from typing import Any

from app.services.corpus_index import CorpusIndex, KeywordIndex
from app.services.ingest_service import IngestService


class AppState:
    corpus_index: CorpusIndex | None = None
    keyword_index: KeywordIndex | None = None
    ingest_service: IngestService | None = None
    job_registry: dict[str, dict[str, Any]] = {}

state = AppState()
