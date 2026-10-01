from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.core.management_access import require_management_access
from app.services.logpresso_environment import (
    LogpressoClient, LogpressoConnectionError, LogpressoEnvironmentStore, suggest_table_mappings,
)
from app.services.store_schema_knowledge import StoreSchemaKnowledge
from app.services.store_table_mapping import StoreTableMapping


router = APIRouter()


def environment_store() -> LogpressoEnvironmentStore:
    return LogpressoEnvironmentStore(settings.logpresso_snapshot_path)


@router.get("/status")
def status():
    snapshot = environment_store().load()
    return {
        "configured": bool(settings.logpresso_base_url and settings.logpresso_api_key),
        "read_only": not settings.logpresso_write_enabled,
        "synced_at": snapshot.get("synced_at"),
        "summary": snapshot.get("summary", {}),
        "partial_failures": snapshot.get("partial_failures", {}),
    }


@router.post("/sync", dependencies=[Depends(require_management_access)])
def sync_environment(request: Request):
    del request
    if not settings.logpresso_base_url or not settings.logpresso_api_key:
        raise HTTPException(status_code=503, detail="Logpresso 연결 정보가 설정되지 않았습니다.")
    try:
        return environment_store().sync(LogpressoClient(
            settings.logpresso_base_url, settings.logpresso_api_key,
            verify_tls=settings.logpresso_verify_tls, timeout=settings.logpresso_timeout_seconds,
        ))
    except (LogpressoConnectionError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/mapping-suggestions")
def mapping_suggestions():
    snapshot = environment_store().load()
    products = StoreSchemaKnowledge.active(settings.store_schema_path).payload.get("products", [])
    return {"items": suggest_table_mappings(snapshot.get("loggers", []), products)}


@router.post("/mapping-suggestions/apply", dependencies=[Depends(require_management_access)])
def apply_mapping_suggestions():
    snapshot = environment_store().load()
    products = StoreSchemaKnowledge.active(settings.store_schema_path).payload.get("products", [])
    suggestions = suggest_table_mappings(snapshot.get("loggers", []), products)
    mapping = StoreTableMapping(settings.store_table_mapping_path)
    for item in suggestions:
        mapping.save(item["product"], item["table"])
    return {"applied": len(suggestions), "items": mapping.list()}
