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
    # Below this confidence, fall back to hybrid. Keep <= vector classifier
    # confidence (0.65) so lookup/default queries can stay on vector.
    router_confidence_threshold: float = 0.6

    # Retrieval
    default_top_k: int = 5
    max_chunks_per_corpus: int = 5000

    # Reranker (HybridService's cross-encoder step)
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    enable_reranker: bool = True

    # Latency budget (Success Criterion 2)
    max_query_latency_seconds: float = 5.0

    # External LLM (OpenAI-compatible). Empty base → Groq default in LLMClient.
    # Gemini free (recommended for full eval): set
    #   llm_api_base=https://generativelanguage.googleapis.com/v1beta/openai/
    #   llm_model=gemini-2.0-flash
    #   llm_api_key=<AI Studio key>
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # GraphRAG (M9 stretch goal): Neo4j connection. Password empty by default
    # -- query.py treats that as "no graph DB configured" and degrades to
    # GraphService(graph_driver=None, nl_to_cypher=None) rather than failing.
    graph_db_uri: str = "bolt://localhost:7687"
    graph_db_user: str = "neo4j"
    graph_db_password: str = ""
    graph_db_database: str = "neo4j"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAGPLATFORM_")


settings = Settings()