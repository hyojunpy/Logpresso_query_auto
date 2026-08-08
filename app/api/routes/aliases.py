from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.alias_store import AliasStore

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
def save_alias(payload: AliasUpsert = Body(...)):
    return AliasStore(settings.db_path).save(payload.phrase, payload.target, payload.kind, payload.scope)


@router.delete("/{kind}/{phrase}")
def delete_alias(kind: str, phrase: str, scope: str = Query(default="")):
    if not AliasStore(settings.db_path).delete(phrase, kind, scope):
        raise HTTPException(status_code=404, detail="alias not found")
    return {"deleted": True}
