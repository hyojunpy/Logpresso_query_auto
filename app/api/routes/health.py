from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.catalog_service import CatalogService
from app.services.indexer import DocumentIndex

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def readiness() -> JSONResponse:
    """Report whether local generation prerequisites are ready without external calls."""
    checks: dict[str, object] = {
        "document_available": settings.doc_path.exists(),
        "index": {"indexed": False, "stale": True, "chunk_count": 0},
        "catalog_available": False,
        "external_call_made": False,
    }
    failures: list[str] = []
    if not checks["document_available"]:
        failures.append("reference_document_missing")
    try:
        index_status = DocumentIndex(settings.db_path).status(settings.doc_path)
        checks["index"] = {
            "indexed": index_status["indexed"],
            "stale": index_status["stale"],
            "chunk_count": index_status["chunk_count"],
        }
        if not index_status["indexed"] or index_status["stale"] or not index_status["chunk_count"]:
            failures.append("document_index_not_ready")
    except Exception:
        failures.append("document_index_unavailable")
    try:
        catalog = CatalogService(settings.catalog_path).load()
        checks["catalog_available"] = bool(catalog and catalog.tables)
    except Exception:
        failures.append("catalog_unavailable")

    ready = not failures
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks, "failures": failures},
    )


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
