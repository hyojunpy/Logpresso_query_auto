from app.services.query_history import append_version, query_diff


def test_query_history_deduplicates_and_limits_versions():
    versions = append_version([], "table logs")
    assert append_version(versions, "table logs") == versions
    assert append_version([str(index) for index in range(10)], "new") == [str(index) for index in range(1, 10)] + ["new"]


def test_query_history_produces_line_diff():
    diff = query_diff("table logs", "table logs\n| limit 100")
    assert "+| limit 100" in diff
