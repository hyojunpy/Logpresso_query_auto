from fastapi.testclient import TestClient

from app.api.main import app


def test_dashboard_design_validate_and_export_api():
    client = TestClient(app)
    response = client.post("/api/v1/dashboards/design", json={"request": "수집 속도 대시보드"})
    assert response.status_code == 200
    dashboard = response.json()
    assert len(dashboard["panels"]) == 1
    assert dashboard["panels"][0]["visualization"] == "metric"

    validation = client.post("/api/v1/dashboards/validate", json=dashboard)
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    exported = client.post("/api/v1/dashboards/export/yaml", json=dashboard)
    assert exported.status_code == 200
    assert "panels:" in exported.json()["content"]
