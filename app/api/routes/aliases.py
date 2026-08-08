from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.alias_store import AliasStore
from app.services.audit_store import AuditStore
from app.core.management_access import audit_actor

router = APIRouter()


class AliasUpsert(BaseModel):
    phrase: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    kind: str = "table"
    scope: str = ""


@router.get("")
def list_aliases(scope: str = Query(default="")):
    """TODO: protect organization vocabulary management with authentication."""
    return {"items": AliasStore(settings.db_path).list(scope or None)}


@router.post("")
def save_alias(request: Request, payload: AliasUpsert = Body(...)):
    saved = AliasStore(settings.db_path).save(payload.phrase, payload.target, payload.kind, payload.scope)
    AuditStore(settings.db_path).record("alias.upsert", f"alias:{payload.kind}", actor=audit_actor(request), metadata={"scope": payload.scope, "phrase_length": len(payload.phrase)})
    return saved


@router.delete("/{kind}/{phrase}")
def delete_alias(request: Request, kind: str, phrase: str, scope: str = Query(default="")):
    if not AliasStore(settings.db_path).delete(phrase, kind, scope):
        raise HTTPException(status_code=404, detail="alias not found")
    AuditStore(settings.db_path).record("alias.delete", f"alias:{kind}", actor=audit_actor(request), metadata={"scope": scope, "phrase_length": len(phrase)})
    return {"deleted": True}
