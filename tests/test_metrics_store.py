from app.services.metrics_store import MetricsStore


def test_metrics_store_keeps_aggregate_counters_only(tmp_path):
    store = MetricsStore(tmp_path / "metrics.db")
    store.increment("generation_generated")
    store.increment("generation_generated")
    assert store.summary() == {"generation_generated": 2}
