from pathlib import Path

import pytest

from app.services.alias_store import AliasImportError, AliasStore


def test_saves_and_updates_alias(tmp_path: Path):
    store = AliasStore(tmp_path / "aliases.db")
    assert store.save("internal firewall", "corp_firewall", "table")["target"] == "corp_firewall"
    assert store.save("internal firewall", "corp_firewall_logs", "table")["target"] == "corp_firewall_logs"
    assert store.list() == [{"phrase": "internal firewall", "target": "corp_firewall_logs", "kind": "table", "scope": ""}]
    assert store.delete("internal firewall", "table") is True
    assert store.list() == []


def test_reports_conflicting_aliases_and_exports_csv(tmp_path: Path):
    store = AliasStore(tmp_path / "aliases.db")
    store.save("방화벽", "firewall_logs", "table", "")
    store.save("방화벽", "edge_firewall_logs", "table", "ENT")

    assert store.diagnostics() == [{
        "code": "alias_conflict", "phrase": "방화벽", "kind": "table",
        "targets": ["firewall_logs", "edge_firewall_logs"], "count": 2,
    }]
    exported = store.export_csv("ENT")
    assert exported.startswith("\ufeffphrase,target,kind,scope")
    assert "edge_firewall_logs" in exported


def test_imports_valid_alias_csv_atomically(tmp_path: Path):
    store = AliasStore(tmp_path / "aliases.db")
    count = store.import_csv_bytes("phrase,target,kind,scope\n방화벽,firewall_logs,table,ENT\n출발지,src_ip,field,\n".encode())

    assert count == 2
    assert {item["target"] for item in store.list("ENT")} == {"firewall_logs", "src_ip"}


def test_previews_new_updated_and_unchanged_aliases(tmp_path: Path):
    store = AliasStore(tmp_path / "aliases.db")
    store.save("방화벽", "old_firewall", "table", "ENT")

    preview = store.preview_csv_bytes("phrase,target,kind,scope\n방화벽,firewall_logs,table,ENT\n출발지,src_ip,field,\n".encode())

    assert preview[0]["change"] == "update"
    assert preview[0]["previous_target"] == "old_firewall"
    assert preview[1]["change"] == "new"


def test_rejects_invalid_alias_csv_without_partial_write(tmp_path: Path):
    store = AliasStore(tmp_path / "aliases.db")
    store.save("기존", "existing_table")

    with pytest.raises(AliasImportError, match="row 3"):
        store.import_csv_bytes("phrase,target,kind\n방화벽,firewall_logs,table\n잘못,bad,unknown\n".encode())

    assert [item["target"] for item in store.list()] == ["existing_table"]
