from fastapi import APIRouter, Depends, HTTPException

from app.core.config import BASE_DIR, settings
from app.core.management_access import require_management_access
from app.services.gold_set import compare_llm_context_limits, run_gold_set as run_gold_set_evaluation
from app.services.llm.ollama_provider import OllamaProvider

router = APIRouter()


@router.post("/gold-set", dependencies=[Depends(require_management_access)])
def run_gold_set():
    """Development-only evaluation endpoint; enable explicitly with ENABLE_DEV_EVALUATION=true."""
    if not settings.enable_dev_evaluation:
        raise HTTPException(status_code=404, detail="Development evaluation is disabled.")
    return run_gold_set_evaluation(settings.db_path, BASE_DIR / "tests" / "fixtures" / "gold_set.json")


@router.post("/gold-set/ollama-context", dependencies=[Depends(require_management_access)])
def compare_ollama_context_limits():
    """Explicit development evaluation. It calls only the configured local Ollama provider."""
    if not settings.enable_dev_evaluation:
        raise HTTPException(status_code=404, detail="Development evaluation is disabled.")
    if settings.llm_provider != "ollama":
        raise HTTPException(status_code=409, detail="LLM_PROVIDER must be ollama for this evaluation.")
    return compare_llm_context_limits(
        settings.db_path,
        BASE_DIR / "tests" / "fixtures" / "gold_set.json",
        OllamaProvider(),
    )
