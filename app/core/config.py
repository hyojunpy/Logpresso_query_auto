from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    app_name = "logpresso-query-assistant"
    docs_dir: Path = BASE_DIR / "docs"
    doc_path: Path = docs_dir / "로그프레소 쿼리.docx"
    data_dir: Path = BASE_DIR / "data"
    db_path: Path = data_dir / "app.db"
    # Separate from the document index so best-effort counters cannot lock it.
    metrics_db_path: Path = data_dir / "metrics.db"
    metrics_retention_days: int = max(1, int(os.getenv("METRICS_RETENTION_DAYS", "30")))
    catalog_path: Path = data_dir / "catalog.json"
    store_schema_path: Path = data_dir / "store-schema.json"
    store_table_mapping_path: Path = data_dir / "store-table-mappings.json"
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock").lower()
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    openai_timeout_seconds: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
    # A timeout falls back to a validated template, so do not leave the UI waiting for minutes.
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45"))
    llm_context_limit: int = max(1, int(os.getenv("LLM_CONTEXT_LIMIT", "4")))
    llm_context_excerpt_chars: int = max(100, int(os.getenv("LLM_CONTEXT_EXCERPT_CHARS", "600")))
    # Keep local-model output short enough for interactive query drafting.
    ollama_num_predict: int = max(1, int(os.getenv("OLLAMA_NUM_PREDICT", "96")))
    ollama_num_ctx: int = max(1_024, int(os.getenv("OLLAMA_NUM_CTX", "4096")))
    enable_llm_intent_fallback: bool = os.getenv("ENABLE_LLM_INTENT_FALLBACK", "true").lower() in {"1", "true", "yes"}
    retrieval_limit: int = int(os.getenv("RETRIEVAL_LIMIT", "8"))
    auto_index_documents: bool = os.getenv("AUTO_INDEX_DOCUMENTS", "true").lower() in {"1", "true", "yes"}
    enable_dev_evaluation: bool = os.getenv("ENABLE_DEV_EVALUATION", "false").lower() in {"1", "true", "yes"}
    enable_external_verification: bool = os.getenv("ENABLE_EXTERNAL_VERIFICATION", "false").lower() in {"1", "true", "yes"}
    verification_url: str | None = os.getenv("LOGPRESSO_VERIFICATION_URL") or None
    verification_token: str | None = os.getenv("LOGPRESSO_VERIFICATION_TOKEN") or None
    verification_timeout_seconds: float = max(1.0, min(float(os.getenv("LOGPRESSO_VERIFICATION_TIMEOUT_SECONDS", "10")), 30.0))
    # Optional shared-deployment boundary. Leave unset for local single-user use.
    management_api_key: str | None = os.getenv("MANAGEMENT_API_KEY") or None
    ui_auth_enabled: bool = os.getenv("UI_AUTH_ENABLED", "false").lower() in {"1", "true", "yes"}
    ui_users_json: str = os.getenv("UI_USERS_JSON", "{}")
    session_idle_minutes: int = max(5, int(os.getenv("SESSION_IDLE_MINUTES", "60")))
    auth_max_failures: int = max(3, int(os.getenv("AUTH_MAX_FAILURES", "5")))
    auth_lockout_minutes: int = max(1, int(os.getenv("AUTH_LOCKOUT_MINUTES", "15")))
    auth_db_path: Path = data_dir / "auth.db"
    log_file: Path = Path(os.getenv("LOG_FILE", str(data_dir / "logs" / "app.jsonl")))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    cors_allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if origin.strip()
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
