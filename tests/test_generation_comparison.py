from app.models.response import GenerateQueryResponse
from app.services.generation_comparison import append_comparison_history, comparison_history_rows, compare_generation_results


def test_comparison_prefers_generated_llm_result_when_rule_needs_clarification():
    rule = GenerateQueryResponse(status="needs_clarification")
    llm = GenerateQueryResponse(status="generated", query="table firewall")
    comparison = compare_generation_results(rule, llm)
    assert comparison["recommended_mode"] == "llm_assisted"
    assert comparison["same_query"] is False


def test_comparison_history_is_bounded_and_exposes_only_summary_rows():
    item = {"recommended_mode": "rule_based", "rule_based": {"status": "generated", "risk_level": "low", "query": "table logs"}, "llm_assisted": {"status": "generated", "risk_level": "medium", "query": "table logs"}}
    history = []
    for _ in range(12):
        history = append_comparison_history(history, item)
    assert len(history) == 10
    assert comparison_history_rows(history)[0] == {
        "recent": 1, "recommended_mode": "rule_based", "rule_status": "generated", "ollama_status": "generated", "rule_risk": "low", "ollama_risk": "medium",
    }
