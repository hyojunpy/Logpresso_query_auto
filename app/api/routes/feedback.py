from fastapi import APIRouter, Body

from app.core.config import settings
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


@router.get("/summary", response_model=FeedbackSummaryResponse)
def feedback_summary():
    """TODO: protect feedback reporting with authentication in shared deployments."""
    return FeedbackStore(settings.db_path).summary()


@router.get("/improvement-candidates", response_model=ImprovementCandidatesResponse)
def improvement_candidates():
    """TODO: protect reporting endpoints with authentication in shared deployments."""
    return {"items": FeedbackStore(settings.db_path).improvement_candidates()}


@router.get("/improvement-report", response_model=ImprovementReportResponse)
def improvement_report():
    """TODO: protect reporting endpoints with authentication in shared deployments."""
    return FeedbackStore(settings.db_path).improvement_report()
