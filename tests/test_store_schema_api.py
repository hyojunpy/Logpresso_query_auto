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
