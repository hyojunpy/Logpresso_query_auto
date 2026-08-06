import json

from fastapi import APIRouter, HTTPException

from app.core.config import BASE_DIR, settings
from app.models.request import Catalog, GenerateQueryRequest, RequestContext
from app.services.indexer import DocumentIndex
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever

router = APIRouter()


@router.post("/gold-set")
def run_gold_set():
    """Development-only evaluation endpoint; enable explicitly with ENABLE_DEV_EVALUATION=true."""
    if not settings.enable_dev_evaluation:
        raise HTTPException(status_code=404, detail="Development evaluation is disabled.")
    cases = json.loads((BASE_DIR / "tests" / "fixtures" / "gold_set.json").read_text(encoding="utf-8"))
    generator = QueryGenerator(Retriever(DocumentIndex(settings.db_path)))
    status_map = {"success": "generated", "clarification": "needs_clarification", "unsupported": "unsupported"}
    results = []
    for case in cases:
        catalog = Catalog.model_validate(case["catalog"])
        context = RequestContext(
            catalog=catalog,
            known_tables=case.get("known_tables", [table.table_name for table in catalog.tables]),
            known_fields=case.get("known_fields", [field.field_name for table in catalog.tables for field in table.fields]),
            known_loggers=case.get("known_loggers", []),
            known_streams=case.get("known_streams", []),
        )
        response = generator.generate(GenerateQueryRequest(request=case["request"], context=context))
        passed = response.status == status_map[case["expected_status"]]
        results.append({"request": case["request"], "expected_status": case["expected_status"], "actual_status": response.status, "passed": passed})
    return {"total": len(results), "passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] for item in results), "results": results}
