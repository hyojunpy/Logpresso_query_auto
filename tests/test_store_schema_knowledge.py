from app.models.request import GenerateQueryRequest, RequestContext
from app.services.store_schema_knowledge import StoreSchemaKnowledge


def test_bundled_catalog_contains_full_store_scope():
    assert StoreSchemaKnowledge.bundled().payload["stats"] == {
        "products": 64,
        "schemas": 470,
        "schemas_with_fields": 154,
        "fields": 2277,
        "raw_formats": 9,
    }


def test_matches_non_secui_product_schema_and_field_aliases():
    enriched = StoreSchemaKnowledge.bundled().enrich(GenerateQueryRequest(
        request="WAPPLES 침입탐지에서 출발지 IP별 위험도 점수를 보여줘",
        context=RequestContext(known_tables=["waf_events"]),
    ))
    assert enriched.context.product == "WAPPLES"
    assert "src_ip별" in enriched.request
    assert "risk_score" in enriched.request
    assert {field.field_name for field in enriched.context.request_catalog.tables[0].fields} >= {
        "src_ip", "risk_score", "log_type"
    }


def test_prefers_longest_product_alias_for_overlapping_names():
    match = StoreSchemaKnowledge.bundled().match("AhnLab TrusGuard IPX의 IPS 로그")
    assert match is not None
    assert match.product == "AhnLab TrusGuard IPX"


def test_does_not_invent_log_type_filter_without_confirmed_discriminator():
    match = StoreSchemaKnowledge.bundled().match("FortiGate Webfilter를 보여줘")
    assert match is not None
    assert match.schema_name == "FortiGate Webfilter"
    assert match.discriminator_field is None


def test_schema_with_multiple_codes_preserves_all_values():
    match = StoreSchemaKnowledge.bundled().match("QueryPie DAC SQL 감사를 보여줘")
    assert match is not None
    assert match.schema_name == "QueryPie SQL 감사"
    assert match.log_types == ("SQL_EXECUTE", "QUERY_AUDIT")
    assert match.discriminator_field is None


def test_generic_deny_still_does_not_activate_store_knowledge():
    payload = GenerateQueryRequest(
        request="firewall_logs에서 action이 deny인 로그 보여줘",
        context=RequestContext(known_tables=["firewall_logs"], known_fields=["action", "_time"]),
    )
    assert StoreSchemaKnowledge.bundled().enrich(payload) == payload
