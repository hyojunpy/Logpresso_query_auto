from fastapi import APIRouter, Body, Depends

from app.core.config import settings
from app.core.management_access import require_management_access
from app.models.request import FeedbackRequest
from app.models.response import (
    FeedbackSaveResponse,
    FeedbackSummaryResponse,
    ImprovementCandidatesResponse,
    ImprovementReportResponse,
)
from app.services.feedback_store import FeedbackStore

router = APIRouter()


@router.post("", response_model=FeedbackSaveResponse)
def create_feedback(payload: FeedbackRequest = Body(...)):
    return FeedbackStore(settings.db_path).save(payload)


@router.get("/summary", response_model=FeedbackSummaryResponse, dependencies=[Depends(require_management_access)])
def feedback_summary():
    return FeedbackStore(settings.db_path).summary()


@router.get("/improvement-candidates", response_model=ImprovementCandidatesResponse, dependencies=[Depends(require_management_access)])
def improvement_candidates():
    return {"items": FeedbackStore(settings.db_path).improvement_candidates()}


@router.get("/improvement-report", response_model=ImprovementReportResponse, dependencies=[Depends(require_management_access)])
def improvement_report():
    return FeedbackStore(settings.db_path).improvement_report()
