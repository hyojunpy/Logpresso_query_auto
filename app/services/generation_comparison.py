from __future__ import annotations

from app.models.response import GenerateQueryResponse


MAX_COMPARISON_HISTORY = 10


def compare_generation_results(rule_based: GenerateQueryResponse, llm_assisted: GenerateQueryResponse) -> dict[str, object]:
    """Return a display-safe comparison. It never executes the generated query."""
    return {
        "rule_based": _summary(rule_based),
        "llm_assisted": _summary(llm_assisted),
        "same_query": rule_based.query == llm_assisted.query,
        "recommended_mode": _recommended_mode(rule_based, llm_assisted),
    }


def append_comparison_history(history: list[dict[str, object]], comparison: dict[str, object]) -> list[dict[str, object]]:
    """Keep a browser-session-only, bounded comparison history."""
    return [*history, comparison][-MAX_COMPARISON_HISTORY:]


def comparison_history_rows(history: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, item in enumerate(reversed(history), start=1):
        rule = item.get("rule_based", {})
        llm = item.get("llm_assisted", {})
        rows.append({
            "recent": index,
            "recommended_mode": item.get("recommended_mode"),
            "rule_status": rule.get("status") if isinstance(rule, dict) else None,
            "ollama_status": llm.get("status") if isinstance(llm, dict) else None,
            "rule_risk": rule.get("risk_level") if isinstance(rule, dict) else None,
            "ollama_risk": llm.get("risk_level") if isinstance(llm, dict) else None,
        })
    return rows


def _summary(response: GenerateQueryResponse) -> dict[str, object]:
    return {
        "status": response.status,
        "query": response.query,
        "risk_level": response.quality.risk_level if response.quality else None,
        "validation_errors": len(response.validation.errors) if response.validation else 0,
        "assumptions": response.assumptions,
    }


def _recommended_mode(rule_based: GenerateQueryResponse, llm_assisted: GenerateQueryResponse) -> str:
    if rule_based.status != "generated" and llm_assisted.status == "generated":
        return "llm_assisted"
    if llm_assisted.status != "generated":
        return "rule_based"
    if (llm_assisted.validation and llm_assisted.validation.errors) and not (rule_based.validation and rule_based.validation.errors):
        return "rule_based"
    return "review_both"
