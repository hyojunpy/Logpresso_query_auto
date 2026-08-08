from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.config import settings
from app.services.audit_store import AuditStore

router = APIRouter()


class AuditEvent(BaseModel):
    action: str
    resource: str
    actor: str | None = None
    metadata: dict[str, object]
    created_at: str


class AuditEventsResponse(BaseModel):
    items: list[AuditEvent]


@router.get("", response_model=AuditEventsResponse)
def list_audit_events(limit: int = Query(default=50, ge=1, le=200)):
    """TODO: restrict this endpoint to platform administrators via the customer identity provider."""
    return {"items": AuditStore(settings.db_path).recent(limit)}
