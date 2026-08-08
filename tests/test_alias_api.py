from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings


def test_alias_csv_import_api_accepts_valid_csv_and_rejects_invalid_csv():
    original_db_path = settings.db_path
    try:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            settings.db_path = Path(tmp) / "aliases.db"
            with TestClient(app) as client:
                valid = client.post(
                    "/api/v1/aliases/import/csv",
                    content="phrase,target,kind,scope\n방화벽,firewall_logs,table,ENT\n",
                    headers={"Content-Type": "text/csv"},
                )
                invalid = client.post(
                    "/api/v1/aliases/import/csv",
                    content="phrase,target,kind\n잘못,bad,unknown\n",
                    headers={"Content-Type": "text/csv"},
                )
                listed = client.get("/api/v1/aliases", params={"scope": "ENT"})
    finally:
        settings.db_path = original_db_path

    assert valid.status_code == 200
    assert valid.json() == {"imported": 1}
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_alias_csv"
    assert listed.json()["items"] == [{"phrase": "방화벽", "target": "firewall_logs", "kind": "table", "scope": "ENT"}]
