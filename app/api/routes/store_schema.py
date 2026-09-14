from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.management_access import audit_actor, require_management_access
from app.services.audit_store import AuditStore
from app.services.store_schema_knowledge import StoreSchemaKnowledge
from app.services.store_schema_update import StoreSchemaUpdate, StoreSchemaUpdateError
from app.services.store_table_mapping import StoreTableMapping


router = APIRouter()


class TableMappingRequest(BaseModel):
    product: str = Field(min_length=1, max_length=200)
    schema_name: str | None = Field(default=None, max_length=300)
    table_name: str = Field(min_length=1, max_length=200)


class RawValidationRequest(BaseModel):
    product: str = Field(min_length=1, max_length=200)
    log_type: str = Field(min_length=1, max_length=200)
    raw_line: str = Field(min_length=1, max_length=100_000)


def knowledge() -> StoreSchemaKnowledge:
    return StoreSchemaKnowledge.active(settings.store_schema_path)


@router.get("/status")
def store_schema_status():
    return knowledge().status()


@router.get("/products")
def store_schema_products():
    return {"items": [{
        "manufacturer": product.get("manufacturer"),
        "product": product.get("name"),
        "schema_count": len(product.get("schemas", [])),
        "raw_format_count": len(product.get("raw_formats", [])),
        "schemas": [schema.get("name") for schema in product.get("schemas", [])],
    } for product in knowledge().payload.get("products", [])]}


@router.get("/search")
def search_store_schema(q: str = Query(min_length=1, max_length=200), limit: int = Query(20, ge=1, le=100)):
    return {"items": knowledge().search(q, limit)}


@router.get("/mappings")
def list_table_mappings():
    return {"items": StoreTableMapping(settings.store_table_mapping_path).list()}


@router.put("/mappings", dependencies=[Depends(require_management_access)])
def save_table_mapping(request: Request, payload: TableMappingRequest):
    try:
        items = StoreTableMapping(settings.store_table_mapping_path).save(
            payload.product, payload.table_name, payload.schema_name
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    AuditStore(settings.db_path).record(
        "store_schema.mapping", payload.product, actor=audit_actor(request),
        metadata={"schema": payload.schema_name, "table": payload.table_name},
    )
    return {"items": items}


@router.post("/raw/validate")
def validate_raw_format(payload: RawValidationRequest):
    return knowledge().validate_raw(payload.product, payload.log_type, payload.raw_line)


@router.post("/import/xlsx", dependencies=[Depends(require_management_access)])
async def import_store_schema(
    request: Request,
    file: UploadFile = File(...),
    apply: bool = Query(False),
):
    content = await file.read()
    updater = StoreSchemaUpdate(settings.store_schema_path)
    try:
        candidate = updater.parse_xlsx(content, file.filename or "store-schema.xlsx")
    except StoreSchemaUpdateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    current = updater.current(StoreSchemaKnowledge.bundled().payload)
    comparison = updater.compare(current, candidate)
    if apply:
        updater.save(candidate)
        AuditStore(settings.db_path).record(
            "store_schema.import", file.filename or "store-schema.xlsx", actor=audit_actor(request),
            metadata=candidate.get("stats", {}),
        )
    return {"applied": apply, "comparison": comparison, "candidate_stats": candidate.get("stats", {})}
