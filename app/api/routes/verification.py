from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.management_access import require_management_access
from app.services.verification_adapter import NoopVerificationAdapter, VerificationResult

router = APIRouter()


class DryRunVerificationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20000)


@router.post("/dry-run", response_model=VerificationResult, dependencies=[Depends(require_management_access)])
def verify_dry_run(payload: DryRunVerificationRequest = Body(...)):
    """Development contract check only; this endpoint never performs external I/O."""
    if not settings.enable_dev_evaluation:
        raise HTTPException(status_code=404, detail="Development verification is disabled.")
    return NoopVerificationAdapter().verify_dry_run(payload.query)
