from app.models.request import GenerateQueryRequest, RequestContext
from app.services.secui_knowledge import SecuiKnowledge


def test_resolves_product_schema_log_type_and_korean_field_aliases():
    enriched = SecuiKnowledge.bundled().enrich(
        GenerateQueryRequest(
            request="블루맥스 NGF 웹 필터에서 출발지 IP별 도메인을 보여줘",
            context=RequestContext(known_tables=["secui_events"]),
        )
    )

    assert enriched.context.product == "BLUEMAX NGF"
    assert "src_ip별" in enriched.request
    assert "domain" in enriched.request
    assert "log_type" in enriched.context.known_fields
    assert enriched.context.request_catalog.tables[0].table_name == "secui_events"
    assert {field.field_name for field in enriched.context.request_catalog.tables[0].fields} >= {
        "src_ip", "log_type"
    }


def test_does_not_guess_ambiguous_schema_without_product():
    match = SecuiKnowledge.bundled().match("감사 로그를 보여줘")
    assert match is None or match.log_type is None


def test_product_only_adds_known_fields_without_inventing_source_table():
    enriched = SecuiKnowledge.bundled().enrich(
        GenerateQueryRequest(request="SECUI MF2의 목적지 IP별 건수를 보여줘")
    )
    assert enriched.context.known_tables == []
    assert "dst_ip별" in enriched.request
    assert "dst_ip" in enriched.context.known_fields


def test_duration_word_is_not_rewritten_as_time_field():
    enriched = SecuiKnowledge.bundled().enrich(
        GenerateQueryRequest(
            request="최근 24시간 블루맥스 NGF 웹 필터를 보여줘",
            context=RequestContext(known_tables=["secui_events"]),
        )
    )
    assert "최근 24시간" in enriched.request
    assert "24_time" not in enriched.request


def test_generic_deny_value_does_not_activate_secui_knowledge():
    payload = GenerateQueryRequest(
        request="firewall_logs에서 action이 deny인 로그 보여줘",
        context=RequestContext(known_tables=["firewall_logs"], known_fields=["action", "_time"]),
    )
    assert SecuiKnowledge.bundled().enrich(payload) == payload
