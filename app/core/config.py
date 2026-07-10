"""Central settings for the RAG platform service.

All values are overridable via environment variables (see .env.example).
Keeping this in one place means the router/retrieval services never read
os.environ directly — they import `settings`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "rag-platform"
    environment: str = "local"

    # Router thresholds
    router_confidence_threshold: float = 0.6  # below this -> fall back to hybrid (Risk 1 mitigation)

    # Retrieval
    default_top_k: int = 5
    max_chunks_per_corpus: int = 5000

    # Reranker (HybridService's cross-encoder step)
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    enable_reranker: bool = True

    # Latency budget (Success Criterion 2)
    max_query_latency_seconds: float = 5.0

    # External services (empty in local/dev; set in host env for deployed target)
    llm_api_base: str = ""
    llm_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAGPLATFORM_")


settings = Settings()