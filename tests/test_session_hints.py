from app.services.session_hints import merge_hints, remove_hint


def test_merges_hints_in_first_seen_order_and_ignores_blanks():
    assert merge_hints(["firewall", ""], ["insa", "firewall", " "]) == ["firewall", "insa"]


def test_removes_only_the_selected_hint():
    assert remove_hint(["firewall", "insa", "auth_logs"], "insa") == ["firewall", "auth_logs"]
