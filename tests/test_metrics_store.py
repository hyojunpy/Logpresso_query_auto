from datetime import UTC, datetime, timedelta

from app.services.metrics_store import MetricsStore


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
