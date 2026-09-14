from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings


def test_store_schema_status_search_and_products():
    client = TestClient(app)
    status = client.get("/api/v1/store-schema/status")
    search = client.get("/api/v1/store-schema/search", params={"q": "포티게이트 웹필터"})
    products = client.get("/api/v1/store-schema/products")

    assert status.status_code == 200
    assert status.json()["schemas"] == 470
    assert search.status_code == 200
    assert any(item["product"] == "FortiGate" for item in search.json()["items"])
    assert products.status_code == 200
    assert len(products.json()["items"]) == 64


def test_store_table_mapping_api_persists_and_lists(tmp_path):
    path = Path(tmp_path) / "mappings.json"
    db_path = Path(tmp_path) / "index.db"
    with patch.object(settings, "store_table_mapping_path", path), patch.object(settings, "db_path", db_path):
        client = TestClient(app)
        saved = client.put("/api/v1/store-schema/mappings", json={
            "product": "AIWAF", "schema_name": "AIWAF Alert", "table_name": "aiwaf_events",
        })
        listed = client.get("/api/v1/store-schema/mappings")

    assert saved.status_code == 200
    assert listed.json()["items"] == [{
        "product": "AIWAF", "schema": "AIWAF Alert", "table": "aiwaf_events",
    }]


def test_store_raw_validation_api():
    response = TestClient(app).post("/api/v1/store-schema/raw/validate", json={
        "product": "AIWAF", "log_type": "AUDIT", "raw_line": "a|b",
    })
    assert response.status_code == 200
    assert response.json()["reason"] == "field_count_mismatch"


def test_store_coverage_detection_and_preflight_api(tmp_path):
    mapping_path = Path(tmp_path) / "mappings.json"
    with patch.object(settings, "store_table_mapping_path", mapping_path):
        client = TestClient(app)
        coverage = client.get("/api/v1/store-schema/coverage", params={"missing_only": "true"})
        detected = client.post("/api/v1/store-schema/raw/detect", json={"raw_line": "AUDIT|a|b"})
        preflight = client.get("/api/v1/store-schema/preflight", params={
            "product": "FortiGate", "schema": "FortiGate Webfilter",
        })

    assert coverage.status_code == 200
    assert len(coverage.json()["items"]) == 316
    assert detected.status_code == 200
    assert detected.json()["items"]
    assert preflight.json()["issues"] == ["fields_unavailable", "table_mapping_missing"]


def test_store_mapping_csv_api_round_trip(tmp_path):
    mapping_path = Path(tmp_path) / "mappings.json"
    db_path = Path(tmp_path) / "app.db"
    with patch.object(settings, "store_table_mapping_path", mapping_path), patch.object(settings, "db_path", db_path):
        client = TestClient(app)
        imported = client.post("/api/v1/store-schema/mappings/import", files={
            "file": ("mappings.csv", b"product,schema,table\nAIWAF,,aiwaf_events\n", "text/csv")
        })
        exported = client.get("/api/v1/store-schema/mappings.csv")

    assert imported.status_code == 200
    assert exported.status_code == 200
    assert "AIWAF,,aiwaf_events" in exported.text


def test_store_excel_import_preview_does_not_write(tmp_path):
    from tests.test_store_schema_update import catalog_workbook

    path = Path(tmp_path) / "store-schema.json"
    with patch.object(settings, "store_schema_path", path):
        response = TestClient(app).post(
            "/api/v1/store-schema/import/xlsx",
            params={"apply": "false"},
            files={"file": ("catalog.xlsx", catalog_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert response.status_code == 200
    assert response.json()["applied"] is False
    assert response.json()["candidate_stats"]["schemas"] == 1
    assert not path.exists()
