from pathlib import Path

from app.services.alias_store import AliasStore


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
