from __future__ import annotations

import json
from pathlib import Path

from app.models.request import Catalog, GenerateQueryRequest, RequestContext
from app.services.indexer import DocumentIndex
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever


def run_gold_set(db_path: Path, fixture_path: Path) -> dict[str, object]:
    """Run fixture-only semantic evaluation. No customer system is contacted."""
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    generator = QueryGenerator(Retriever(DocumentIndex(db_path)))
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
            "actual_status": response.status, "passed": all(checks.values()),
            "failed_checks": [name for name, passed in checks.items() if not passed],
        })
    return {"total": len(results), "passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] for item in results), "results": results}
