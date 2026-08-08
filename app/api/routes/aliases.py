from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.alias_store import AliasImportError, AliasStore
from app.services.audit_store import AuditStore
from app.core.management_access import audit_actor, require_management_access

router = APIRouter()


class AliasUpsert(BaseModel):
    phrase: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    kind: str = "table"
    scope: str = ""


@router.get("", dependencies=[Depends(require_management_access)])
def list_aliases(scope: str = Query(default="")):
    return {"items": AliasStore(settings.db_path).list(scope or None)}


@router.get("/diagnostics", dependencies=[Depends(require_management_access)])
def alias_diagnostics():
    return {"items": AliasStore(settings.db_path).diagnostics()}


@router.get("/export/csv", response_class=Response, dependencies=[Depends(require_management_access)])
def export_aliases(scope: str = Query(default="")):
    return Response(
        content=AliasStore(settings.db_path).export_csv(scope or None),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="logpresso-aliases.csv"'},
    )


@router.post("/import/csv", dependencies=[Depends(require_management_access)])
def import_aliases(request: Request, content: str = Body(..., media_type="text/csv")):
    try:
        count = AliasStore(settings.db_path).import_csv_bytes(content.encode("utf-8"))
    except AliasImportError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_alias_csv", "message": str(error)}) from error
    AuditStore(settings.db_path).record("alias.import_csv", "aliases", actor=audit_actor(request), metadata={"count": count})
    return {"imported": count}


@router.post("", dependencies=[Depends(require_management_access)])
def save_alias(request: Request, payload: AliasUpsert = Body(...)):
    saved = AliasStore(settings.db_path).save(payload.phrase, payload.target, payload.kind, payload.scope)
    AuditStore(settings.db_path).record("alias.upsert", f"alias:{payload.kind}", actor=audit_actor(request), metadata={"scope": payload.scope, "phrase_length": len(payload.phrase)})
    return saved


@router.delete("/{kind}/{phrase}", dependencies=[Depends(require_management_access)])
def delete_alias(request: Request, kind: str, phrase: str, scope: str = Query(default="")):
    if not AliasStore(settings.db_path).delete(phrase, kind, scope):
        raise HTTPException(status_code=404, detail="alias not found")
    AuditStore(settings.db_path).record("alias.delete", f"alias:{kind}", actor=audit_actor(request), metadata={"scope": scope, "phrase_length": len(phrase)})
    return {"deleted": True}
