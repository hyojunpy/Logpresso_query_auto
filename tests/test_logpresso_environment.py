import json

import httpx
import pytest

from app.services.logpresso_environment import (
    LogpressoClient, LogpressoConnectionError, LogpressoEnvironmentStore,
    resolve_synced_table, suggest_table_mappings,
)


def test_client_paginates_and_redacts_sensitive_values():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"total_count": 1, "loggers": [{
            "name": "AXGATE NGFW", "table_name": "axgate_events",
            "configs": {"password": "never-store"},
        }]})

    client = LogpressoClient("https://logpresso.local", "secret", transport=httpx.MockTransport(handler))
    assert client.loggers() == [{"name": "AXGATE NGFW", "table_name": "axgate_events"}]


def test_connection_error_does_not_leak_response_or_key():
    client = LogpressoClient(
        "https://logpresso.local", "secret",
        transport=httpx.MockTransport(lambda request: httpx.Response(401, text="secret details")),
    )
    with pytest.raises(LogpressoConnectionError) as error:
        client.loggers()
    assert "secret" not in str(error.value)
    assert "HTTP 401" in str(error.value)


def test_store_sync_keeps_safe_snapshot_and_partial_failures(tmp_path):
    class Stub:
        def loggers(self): return [{"name": "AXGATE NGFW", "table_name": "axgate_events", "status": "running"}]
        def log_schemas(self): return []
        def parsers(self): raise LogpressoConnectionError("권한 없음")
        def tables(self): return [{"table_name": "axgate_events"}]
        def logger_models(self, loggers): return []

    path = tmp_path / "environment.json"
    payload = LogpressoEnvironmentStore(path).sync(Stub())
    assert payload["summary"]["running"] == 1
    assert payload["partial_failures"] == {"parsers": "권한 없음"}
    assert json.loads(path.read_text(encoding="utf-8"))["loggers"][0]["table_name"] == "axgate_events"


def test_mapping_suggestions_and_unique_resolution():
    loggers = [{"name": "AXGATE NGFW collector", "table_name": "axgate_events"}]
    products = [{"name": "AXGATE NGFW (NF)"}, {"name": "AXGATE SSL VPN"}, {"name": "FortiGate"}]
    assert suggest_table_mappings(loggers, products)[0]["product"] == "AXGATE NGFW (NF)"
    assert resolve_synced_table({"loggers": loggers}, "axgate ngfw") == "axgate_events"
