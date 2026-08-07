from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/dry-run")
def dry_run_status() -> dict[str, object]:
    """Connection preparation only. No Logpresso request is issued from this endpoint."""
    return {
        "status": "preview_ready",
        "execution_enabled": False,
        "external_call_made": False,
        "provider": settings.llm_provider,
        "model": settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model,
        "checks": ["query validation", "catalog validation when available", "manual execution only"],
    }
