from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings
from app.services.metrics_store import MetricsStore


def test_metrics_api_returns_aggregate_counters_without_raw_content():
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with patch.object(settings, "metrics_db_path", Path(tmp) / "metrics.db"):
            client = TestClient(app)
            assert client.get("/api/v1/health").status_code == 200
            response = client.get("/api/v1/internal/metrics")

    assert response.status_code == 200
    assert response.json()["contains_raw_content"] is False
    assert response.json()["metrics"]["http_status_200"] >= 1
    assert response.json()["retention_days"] >= 1
    assert response.json()["items"][0]["label"]
    assert response.json()["daily_items"][0]["day"]


def test_metrics_failure_does_not_break_a_request():
    with patch("app.api.main.MetricsStore.increment", side_effect=OSError("locked")):
        response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200


def test_generate_ollama_fallback_records_only_timing_buckets():
    request_text = "최근 24시간 firewall_logs에서 차단 로그 보여줘"
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with patch.object(settings, "metrics_db_path", Path(tmp) / "metrics.db"), patch.object(
            settings, "llm_provider", "ollama"
        ), patch(
            "app.services.llm.ollama_provider.OllamaProvider.generate_json",
            return_value={
                "status": "error",
                "error_type": "timeout",
                "timing": {"client_duration_ms": 1_200, "response": request_text},
            },
        ):
            response = TestClient(app).post(
                "/api/v1/query/generate",
                json={
                    "request": request_text,
                    "context": {"known_tables": ["firewall_logs"], "known_fields": ["action", "_time"]},
                },
            )
            metrics = MetricsStore(settings.metrics_db_path).summary()

    assert response.status_code == 200
    assert response.json()["status"] == "generated"
    assert response.json()["debug"]["llm_error_type"] == "timeout"
    assert metrics["generation_llm_fallback"] == 1
    assert metrics["ollama_client_duration_ms_lt_5000ms"] == 1
    assert request_text not in str(metrics)
