from __future__ import annotations

import json
from pathlib import Path

from app.models.request import Catalog, GenerateQueryRequest, RequestContext
from app.services.indexer import DocumentIndex
from app.services.llm.base import LLMProvider
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever


def run_gold_set(
    db_path: Path,
    fixture_path: Path,
    llm: LLMProvider | None = None,
    llm_context_limit: int | None = None,
    llm_context_excerpt_chars: int | None = None,
) -> dict[str, object]:
    """Run fixture-only semantic evaluation. No customer system is contacted."""
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    generator = QueryGenerator(
        Retriever(DocumentIndex(db_path)),
        llm=llm,
        llm_context_limit=llm_context_limit,
        llm_context_excerpt_chars=llm_context_excerpt_chars,
    )
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
        query = response.query or ""
        diagnostic_codes = {item.code for item in (response.quality.diagnostics if response.quality else [])}
        checks = {
            "status": response.status == status_map[case["expected_status"]],
            "keywords": all(keyword in query for keyword in case["keywords"]),
            "warnings": set(case["warning_codes"]).issubset(diagnostic_codes),
            "forbidden": not (set(case["forbidden"]) & diagnostic_codes),
        }
        results.append({
            "request": case["request"], "expected_status": case["expected_status"],
            "actual_status": response.status,
            "validation_valid": bool(response.validation and response.validation.valid),
            "passed": all(checks.values()),
            "failed_checks": [name for name, passed in checks.items() if not passed],
        })
    return {"total": len(results), "passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] for item in results), "results": results}


def compare_llm_context_limits(db_path: Path, fixture_path: Path, llm: LLMProvider) -> dict[str, dict[str, int]]:
    """Compare bounded and retrieved-context generation using only fixture cases."""
    from app.core.config import settings

    bounded = run_gold_set(db_path, fixture_path, llm=llm)
    retrieved_context = run_gold_set(
        db_path,
        fixture_path,
        llm=llm,
        llm_context_limit=settings.retrieval_limit,
        llm_context_excerpt_chars=1_000_000,
    )
    return {
        "bounded": _evaluation_summary(bounded),
        "retrieved_context": _evaluation_summary(retrieved_context),
    }


def _evaluation_summary(result: dict[str, object]) -> dict[str, int]:
    items = result["results"]
    assert isinstance(items, list)
    return {
        "total": int(result["total"]),
        "generated": sum(item["actual_status"] == "generated" for item in items),
        "validation_passed": sum(item["validation_valid"] for item in items),
        "semantic_passed": int(result["passed"]),
        "semantic_failed": int(result["failed"]),
    }
