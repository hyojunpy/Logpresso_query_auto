from pathlib import Path

from app.services.alias_store import AliasStore


def test_saves_and_updates_alias(tmp_path: Path):
    store = AliasStore(tmp_path / "aliases.db")
    assert store.save("internal firewall", "corp_firewall", "table")["target"] == "corp_firewall"
    assert store.save("internal firewall", "corp_firewall_logs", "table")["target"] == "corp_firewall_logs"
    assert store.list() == [{"phrase": "internal firewall", "target": "corp_firewall_logs", "kind": "table"}]
