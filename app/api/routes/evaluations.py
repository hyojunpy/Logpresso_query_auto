from fastapi import APIRouter, Depends, HTTPException

from app.core.config import BASE_DIR, settings
from app.core.management_access import require_management_access
from app.services.gold_set import run_gold_set

router = APIRouter()


@router.post("/gold-set", dependencies=[Depends(require_management_access)])
def run_gold_set():
    """Development-only evaluation endpoint; enable explicitly with ENABLE_DEV_EVALUATION=true."""
    if not settings.enable_dev_evaluation:
        raise HTTPException(status_code=404, detail="Development evaluation is disabled.")
    return run_gold_set(settings.db_path, BASE_DIR / "tests" / "fixtures" / "gold_set.json")
