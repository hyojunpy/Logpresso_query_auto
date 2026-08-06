from fastapi import APIRouter, Body

from app.core.config import settings
from app.models.request import FeedbackRequest
from app.services.feedback_store import FeedbackStore

router = APIRouter()


@router.post("")
def create_feedback(payload: FeedbackRequest = Body(...)):
    return FeedbackStore(settings.db_path).save(payload)


@router.get("/summary")
def feedback_summary():
    """TODO: protect feedback reporting with authentication in shared deployments."""
    return FeedbackStore(settings.db_path).summary()
