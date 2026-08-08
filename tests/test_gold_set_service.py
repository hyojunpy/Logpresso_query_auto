from pathlib import Path

from app.services.gold_set import run_gold_set
from tests.support import shared_index


def test_gold_set_service_returns_semantic_check_breakdown():
    result = run_gold_set(shared_index().db_path, Path("tests") / "fixtures" / "gold_set.json")

    assert result["total"] >= 10
    assert result["failed"] == 0
    assert all("failed_checks" in item for item in result["results"])
