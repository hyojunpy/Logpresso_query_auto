from pathlib import Path

from app.services.gold_set import compare_llm_context_limits, run_gold_set
from app.services.llm.mock_provider import MockProvider
from tests.support import shared_index


def test_gold_set_service_returns_semantic_check_breakdown():
    result = run_gold_set(shared_index().db_path, Path("tests") / "fixtures" / "gold_set.json")

    assert result["total"] >= 10
    assert result["failed"] == 0
    assert all("failed_checks" in item for item in result["results"])


def test_gold_set_context_comparison_reports_aggregate_quality_counts():
    result = compare_llm_context_limits(
        shared_index().db_path,
        Path("tests") / "fixtures" / "gold_set.json",
        MockProvider(),
    )

    assert set(result) == {"bounded", "retrieved_context"}
    assert result["bounded"]["total"] >= 10
    assert result["bounded"]["validation_passed"] >= 10
