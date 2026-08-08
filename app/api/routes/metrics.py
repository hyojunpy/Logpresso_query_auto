from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.management_access import require_management_access
from app.services.metrics_store import MetricsStore

router = APIRouter()

@router.get("", dependencies=[Depends(require_management_access)])
def metrics_summary():
    return {"metrics": MetricsStore(settings.metrics_db_path).summary(), "contains_raw_content": False}
