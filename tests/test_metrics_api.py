from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings


def test_metrics_api_returns_aggregate_counters_without_raw_content():
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with patch.object(settings, "metrics_db_path", Path(tmp) / "metrics.db"):
            client = TestClient(app)
            assert client.get("/api/v1/health").status_code == 200
            response = client.get("/api/v1/internal/metrics")

    assert response.status_code == 200
    assert response.json()["contains_raw_content"] is False
    assert response.json()["metrics"]["http_status_200"] >= 1


def test_metrics_failure_does_not_break_a_request():
    with patch("app.api.main.MetricsStore.increment", side_effect=OSError("locked")):
        response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
