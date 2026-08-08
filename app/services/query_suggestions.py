from __future__ import annotations

import re


def apply_safe_suggestion(query: str, diagnostic_code: str) -> str | None:
    """Apply a deterministic, review-only improvement to an editable draft."""
    if diagnostic_code == "missing_result_limit" and not re.search(r"\blimit\s*=?\d+", query, re.IGNORECASE):
        return query.rstrip() + "\n| limit 100"
    if diagnostic_code in {"missing_time_range", "fulltext_without_time_range"} and not re.search(r"\b(?:duration|from|to|window)=", query, re.IGNORECASE):
        if re.search(r"^table\s+", query, re.IGNORECASE | re.MULTILINE):
            return re.sub(r"^table\s+", "table duration=24h ", query, count=1, flags=re.IGNORECASE | re.MULTILINE)
        if re.search(r"^fulltext\s+", query, re.IGNORECASE | re.MULTILINE):
            return re.sub(r"^fulltext\s+", "fulltext duration=24h ", query, count=1, flags=re.IGNORECASE | re.MULTILINE)
    if diagnostic_code == "aggregation_not_sorted" and re.search(r"\|\s*(?:stats|rollup|timechart)\b", query, re.IGNORECASE) and not re.search(r"\|\s*sort\b", query, re.IGNORECASE):
        return query.rstrip() + "\n| sort -count"
    return None
