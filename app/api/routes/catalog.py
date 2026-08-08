import csv
import io

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response

from app.core.config import settings
from app.models.request import CatalogUpsertRequest
from app.models.request import Catalog
from app.services.catalog_import import CatalogImportError, catalog_from_csv_bytes
from app.services.audit_store import AuditStore
from app.core.management_access import audit_actor, require_management_access
from fastapi import HTTPException
from app.services.catalog_service import CatalogService

router = APIRouter()


@router.post("/import/csv", response_model=Catalog, dependencies=[Depends(require_management_access)])
def import_catalog_csv(request: Request, content: str = Body(..., media_type="text/csv")):
    try:
        catalog = catalog_from_csv_bytes(content.encode("utf-8"))
    except CatalogImportError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_catalog_csv", "message": str(error)}) from error
    saved = CatalogService(settings.catalog_path).save(catalog)
    AuditStore(settings.db_path).record("catalog.import_csv", "catalog", actor=audit_actor(request), metadata={"table_count": len(saved.tables)})
    return saved


@router.get("/export/csv", response_class=Response, dependencies=[Depends(require_management_access)])
def export_catalog_csv(request: Request):
    catalog = CatalogService(settings.catalog_path).load()
    AuditStore(settings.db_path).record("catalog.export_csv", "catalog", actor=audit_actor(request), metadata={"table_count": len(catalog.tables) if catalog else 0})
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["table_name", "node", "namespace", "table_description", "field_name", "field_type", "nullable", "description"])
    writer.writeheader()
    for table in (catalog.tables if catalog else []):
        if not table.fields:
            writer.writerow({"table_name": table.table_name, "node": table.node or "", "namespace": table.namespace or "", "table_description": table.description or "", "field_name": "", "field_type": "unknown", "nullable": "", "description": ""})
        for field in table.fields:
            writer.writerow({
                "table_name": table.table_name,
                "node": table.node or "",
                "namespace": table.namespace or "",
                "table_description": table.description or "",
                "field_name": field.field_name,
                "field_type": field.field_type,
                "nullable": "true" if field.nullable is True else "false" if field.nullable is False else "",
                "description": field.description or "",
            })
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="logpresso-catalog.csv"'},
    )


@router.get("/backups", dependencies=[Depends(require_management_access)])
def list_catalog_backups():
    return {"items": CatalogService(settings.catalog_path).backups()}


@router.post("/backups/{name}/restore", response_model=Catalog, dependencies=[Depends(require_management_access)])
def restore_catalog_backup(request: Request, name: str):
    try:
        saved = CatalogService(settings.catalog_path).restore(name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="catalog backup not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid catalog backup name") from error
    AuditStore(settings.db_path).record("catalog.restore", "catalog", actor=audit_actor(request), metadata={"backup": name, "table_count": len(saved.tables)})
    return saved


@router.get("", response_model=Catalog)
def get_catalog():
    catalog = CatalogService(settings.catalog_path).load()
    return catalog or {"tables": [], "source": "unknown"}


@router.put("", response_model=Catalog, dependencies=[Depends(require_management_access)])
def put_catalog(request: Request, payload: CatalogUpsertRequest = Body(...)):
    saved = CatalogService(settings.catalog_path).save(payload.catalog)
    AuditStore(settings.db_path).record("catalog.upsert", "catalog", actor=audit_actor(request), metadata={"table_count": len(saved.tables), "source": saved.source})
    return saved
