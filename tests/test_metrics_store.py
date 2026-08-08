from datetime import UTC, datetime, timedelta

from app.services.metrics_store import MetricsStore, metric_label


def test_metrics_store_keeps_aggregate_counters_only(tmp_path):
    store = MetricsStore(tmp_path / "metrics.db")
    store.increment("generation_generated")
    store.increment("generation_generated")
    assert store.summary() == {"generation_generated": 2}


def test_metrics_store_removes_counters_outside_retention_window(tmp_path):
    store = MetricsStore(tmp_path / "metrics.db", retention_days=2)
    now = datetime.now(UTC)

    store.increment("old", occurred_at=now - timedelta(days=3))
    store.increment("current", occurred_at=now)

    assert store.summary() == {"current": 1}


def test_metric_labels_are_human_readable_for_known_counters():
    assert metric_label("generation_generated") == "쿼리 생성 완료"
    assert metric_label("http_status_422") == "HTTP 422 응답"


def test_metrics_store_returns_bounded_daily_summary(tmp_path):
    store = MetricsStore(tmp_path / "metrics.db", retention_days=3)
    now = datetime.now(UTC)
    store.increment("old", occurred_at=now - timedelta(days=3))
    store.increment("recent", occurred_at=now - timedelta(days=1))
    store.increment("current", occurred_at=now)

    items = store.daily_summary(days=2)

    assert [item["metric"] for item in items] == ["current", "recent"]
