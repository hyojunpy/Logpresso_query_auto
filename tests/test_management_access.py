from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings


def test_management_routes_remain_available_when_key_is_not_configured():
    with patch.object(settings, "management_api_key", None):
        response = TestClient(app).get("/api/v1/aliases")

    assert response.status_code == 200


def test_management_routes_reject_missing_or_wrong_api_key():
    client = TestClient(app)
    with patch.object(settings, "management_api_key", "test-management-secret"):
        missing = client.get("/api/v1/aliases")
        wrong = client.get("/api/v1/aliases", headers={"X-Management-API-Key": "wrong"})
        allowed = client.get("/api/v1/aliases", headers={"X-Management-API-Key": "test-management-secret"})

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "ApiKey"
    assert wrong.status_code == 401
    assert allowed.status_code == 200


def test_management_key_is_allowed_by_cors_preflight():
    response = TestClient(app).options(
        "/api/v1/catalog",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "X-Management-API-Key, Content-Type",
        },
    )

    assert response.status_code == 200
    assert "x-management-api-key" in response.headers["access-control-allow-headers"].lower()
