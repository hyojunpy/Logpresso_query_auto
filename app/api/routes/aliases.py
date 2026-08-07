from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.alias_store import AliasStore

router = APIRouter()


class AliasUpsert(BaseModel):
    phrase: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    kind: str = "table"


@router.get("")
def list_aliases():
    """TODO: protect organization vocabulary management with authentication."""
    return {"items": AliasStore(settings.db_path).list()}


@router.post("")
def save_alias(payload: AliasUpsert = Body(...)):
    return AliasStore(settings.db_path).save(payload.phrase, payload.target, payload.kind)
