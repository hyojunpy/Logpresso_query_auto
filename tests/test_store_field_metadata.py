from scripts.store_field_metadata import derived_display_name, enrich_field_metadata, enrich_payload


def test_derives_korean_security_field_labels_and_aliases():
    assert derived_display_name("nat_src_ip") == "NAT 출발지 IP"
    display, aliases = enrich_field_metadata("event_count")
    assert display == "이벤트 건수"
    assert "이벤트건수" in aliases
    display, aliases = enrich_field_metadata("x")
    assert display == "X"
    assert aliases == ["X 필드"]


def test_reuses_existing_metadata_for_repeated_fields_and_fills_every_field():
    payload = {"products": [{"schemas": [
        {"fields": [{"name": "src_ip", "display_name": "출발지 주소", "aliases": ["소스 IP"]}]},
        {"fields": [{"name": "src_ip", "display_name": "", "aliases": []},
                    {"name": "vendor_custom_code", "display_name": "", "aliases": []}]},
    ]}]}
    enrich_payload(payload)
    fields = [field for schema in payload["products"][0]["schemas"] for field in schema["fields"]]
    assert fields[1]["display_name"] == "출발지 주소"
    assert "소스 IP" in fields[1]["aliases"]
    assert all(field["display_name"] and field["aliases"] for field in fields)
