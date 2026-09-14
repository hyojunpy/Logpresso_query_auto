import json

import pytest

from app.services.store_table_mapping import StoreTableMapping


def test_mapping_resolves_schema_before_product_default(tmp_path):
    store = StoreTableMapping(tmp_path / "mappings.json")
    store.save("FortiGate", "fortigate_all")
    store.save("FortiGate", "fortigate_web", "FortiGate Webfilter")

    assert store.resolve("FortiGate", "FortiGate Webfilter") == "fortigate_web"
    assert store.resolve("FortiGate", "FortiGate Traffic") == "fortigate_all"
    assert len(json.loads((tmp_path / "mappings.json").read_text(encoding="utf-8"))["mappings"]) == 2


def test_mapping_rejects_query_fragments_as_table_names(tmp_path):
    with pytest.raises(ValueError):
        StoreTableMapping(tmp_path / "mappings.json").save("FortiGate", "logs | search true")


def test_mapping_delete_is_scoped_to_product_and_schema(tmp_path):
    store = StoreTableMapping(tmp_path / "mappings.json")
    store.save("A", "a_default")
    store.save("A", "a_detail", "Detail")
    store.delete("A", "Detail")

    assert store.resolve("A", "Detail") == "a_default"
    assert len(store.list()) == 1
