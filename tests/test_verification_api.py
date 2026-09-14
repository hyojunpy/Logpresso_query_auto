from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings


def test_development_dry_run_endpoint_is_disabled_by_default():
    with patch.object(settings, "enable_dev_evaluation", False), patch.object(settings, "enable_external_verification", False):
        response = TestClient(app).post("/api/v1/internal/verification/dry-run", json={"query": "table firewall_logs"})

    assert response.status_code == 404


def test_development_dry_run_returns_noop_result_without_external_call():
    with patch.object(settings, "enable_dev_evaluation", True), patch.object(settings, "enable_external_verification", False):
        response = TestClient(app).post("/api/v1/internal/verification/dry-run", json={"query": "table firewall_logs"})

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"
    assert response.json()["external_call_made"] is False
    assert response.json()["adapter"] == "noop"


def test_external_dry_run_is_used_only_when_explicitly_enabled():
    with patch.object(settings, "enable_external_verification", True), patch.object(
        settings, "verification_url", "https://logpresso.internal/dry-run"
    ), patch("app.api.routes.verification.HttpDryRunVerificationAdapter.verify_dry_run") as verify:
        verify.return_value = {"status": "accepted", "message": "ok", "diagnostics": [], "external_call_made": True, "adapter": "http_dry_run"}
        response = TestClient(app).post(
            "/api/v1/internal/verification/dry-run", json={"query": "table firewall_logs"}
        )

    assert response.status_code == 200
    assert response.json()["adapter"] == "http_dry_run"
