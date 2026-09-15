from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes import dashboards as dashboard_routes


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


def test_dashboard_storage_analysis_and_deployment_plan_api(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_routes.settings, "dashboard_db_path", tmp_path / "dashboards.db")
    client = TestClient(app)
    dashboard = client.post("/api/v1/dashboards/design", json={"request": "수집 속도 대시보드"}).json()

    saved = client.post("/api/v1/dashboards", json={"dashboard": dashboard, "change_note": "first"})
    assert saved.status_code == 200
    dashboard_id = saved.json()["id"]
    assert client.get("/api/v1/dashboards").json()["items"][0]["id"] == dashboard_id

    dashboard["title"] = "수집 속도 변경"
    updated = client.put(f"/api/v1/dashboards/{dashboard_id}", json={"dashboard": dashboard, "change_note": "rename"})
    assert updated.json()["revision"] == 2
    assert "수집 속도 변경" in client.get(f"/api/v1/dashboards/{dashboard_id}/diff?old=1&new=2").json()["content"]

    cloned = client.post(f"/api/v1/dashboards/{dashboard_id}/clone", json={"title": "복제본"})
    assert cloned.json()["dashboard"]["title"] == "복제본"
    restored = client.post(f"/api/v1/dashboards/{dashboard_id}/restore", json={"revision": 1})
    assert restored.json()["revision"] == 3

    analysis = client.post("/api/v1/dashboards/analyze", json=dashboard)
    assert analysis.status_code == 200
    plan = client.post("/api/v1/dashboards/deployment-plan?base_url=https://10.11.12.14", json=dashboard)
    assert plan.status_code == 200
    assert plan.json()["target"]["base_url"] == "https://10.11.12.14"

    assert client.delete(f"/api/v1/dashboards/{dashboard_id}").status_code == 204
    assert client.get(f"/api/v1/dashboards/{dashboard_id}").status_code == 404
