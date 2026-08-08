from app.services.audit_store import AuditStore


def test_records_management_metadata_without_request_or_query_content(tmp_path):
    store = AuditStore(tmp_path / "audit.db")
    store.record("catalog.import_csv", "catalog", actor="catalog-admin", metadata={"table_count": 2})
    event = store.recent()[0]
    assert event["action"] == "catalog.import_csv"
    assert event["actor"] == "catalog-admin"
    assert event["metadata"] == {"table_count": 2}
