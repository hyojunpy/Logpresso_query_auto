from functools import lru_cache
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings:
    app_name = "logpresso-query-assistant"
    docs_dir: Path = BASE_DIR / "docs"
    doc_path: Path = docs_dir / "로그프레소 쿼리.docx"
    data_dir: Path = BASE_DIR / "data"
    db_path: Path = data_dir / "app.db"
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock").lower()
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    openai_timeout_seconds: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    retrieval_limit: int = int(os.getenv("RETRIEVAL_LIMIT", "8"))
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
