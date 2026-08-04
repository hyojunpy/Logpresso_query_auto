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
    retrieval_limit: int = int(os.getenv("RETRIEVAL_LIMIT", "8"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

