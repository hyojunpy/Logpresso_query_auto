from app.services.query_suggestions import apply_safe_suggestion


def test_applies_only_deterministic_review_suggestions():
    assert apply_safe_suggestion("table firewall_logs", "missing_result_limit") == "table firewall_logs\n| limit 100"
    assert apply_safe_suggestion("table firewall_logs", "missing_time_range") == "table duration=24h firewall_logs"
    assert apply_safe_suggestion("table firewall_logs\n| stats count by src_ip", "aggregation_not_sorted").endswith("| sort -count")


def test_does_not_apply_ambiguous_or_duplicate_suggestion():
    assert apply_safe_suggestion("table duration=1h firewall_logs", "missing_time_range") is None
    assert apply_safe_suggestion("table firewall_logs", "join_without_pre_filter") is None
