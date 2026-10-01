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


def test_explicit_product_and_schema_hints_select_catalog_without_names_in_request():
    match = StoreSchemaKnowledge.bundled().match(
        "최근 24시간 출발지 IP별 건수",
        product_hint="AIWAF",
        schema_hint="AIWAF Alert",
    )
    assert match is not None
    assert match.product == "AIWAF"
    assert match.schema_name == "AIWAF Alert"
    assert ("출발지 IP", "src_ip") in match.replacements


def test_field_display_names_and_aliases_are_case_insensitive():
    knowledge = StoreSchemaKnowledge.bundled()
    payload = GenerateQueryRequest(
        request="최근 24시간 SrC Ip별 건수를 보여줘",
        context=RequestContext(
            known_tables=["secui_events"],
            store_product="AIWAF",
            store_schema="AIWAF Alert",
        ),
    )
    enriched = knowledge.enrich(payload)
    assert "src_ip별" in enriched.request


def test_search_supports_korean_aliases_and_typo_similarity():
    knowledge = StoreSchemaKnowledge.bundled()
    assert any(item["product"] == "FortiGate" for item in knowledge.search("포티게이트 웹필터"))
    assert any(item["product"] == "QueryPie DAC" for item in knowledge.search("쿼리파이 SQL 감사"))


def test_status_reports_coverage_gaps():
    status = StoreSchemaKnowledge.bundled().status()
    assert status["schemas_without_fields"] == 470 - 154
    assert status["products_with_raw_formats"] == 3
    assert status["manufacturers"] > 10


def test_raw_pipe_format_validation_reports_field_counts():
    knowledge = StoreSchemaKnowledge.bundled()
    product = next(item for item in knowledge.payload["products"] if item["name"] == "AIWAF")
    template = next(item for item in product["raw_formats"] if item["log_type"] == "AUDIT")["template"]
    expected_count = len(template.split("|"))

    valid = knowledge.validate_raw("AIWAF", "AUDIT", "|".join(["value"] * expected_count))
    invalid = knowledge.validate_raw("AIWAF", "AUDIT", "too|short")

    assert valid["valid"] is True
    assert valid["delimiter"] == "pipe"
    assert invalid["valid"] is False
    assert invalid["reason"] == "field_count_mismatch"


def test_raw_backtick_and_whitespace_formats_are_supported():
    knowledge = StoreSchemaKnowledge.bundled()
    genian = next(item for item in knowledge.payload["products"] if item["name"] == "Genian EDR")
    threat = genian["raw_formats"][0]
    count = len(__import__("re").findall(r"%\{([^}]+)\}", threat["template"]))
    result = knowledge.validate_raw("Genian EDR", threat["log_type"], "THREAT:" + "`".join(["x"] * count))
    assert result["valid"] is True
    assert result["delimiter"] == "backtick"

    eprism = next(item for item in knowledge.payload["products"] if item["name"] == "ePrism SSL VA")
    ssl = eprism["raw_formats"][0]
    count = len(__import__("re").findall(r"%[A-Za-z0-9_]+", ssl["template"]))
    result = knowledge.validate_raw("ePrism SSL VA", ssl["log_type"], " ".join(["x"] * count))
    assert result["valid"] is True
    assert result["delimiter"] == "whitespace"


def test_raw_detection_ranks_exact_public_format_first():
    knowledge = StoreSchemaKnowledge.bundled()
    product = next(item for item in knowledge.payload["products"] if item["name"] == "AIWAF")
    template = next(item for item in product["raw_formats"] if item["log_type"] == "AUDIT")["template"]
    raw_line = "AUDIT|" + "|".join(["value"] * (len(template.split("|")) - 1))

    candidates = knowledge.detect_raw(raw_line)

    assert candidates[0]["product"] == "AIWAF"
    assert candidates[0]["log_type"] == "AUDIT"
    assert candidates[0]["valid"] is True


def test_coverage_and_preflight_expose_operational_gaps():
    knowledge = StoreSchemaKnowledge.bundled()
    missing = knowledge.coverage(missing_only=True)
    assert len(missing) == 316
    assert all(item["field_count"] == 0 for item in missing)

    blocked = knowledge.preflight("FortiGate", "FortiGate Webfilter", None)
    assert blocked["ready"] is False
    assert set(blocked["issues"]) == {"fields_unavailable", "table_mapping_missing"}

    ready = knowledge.preflight("AIWAF", "AIWAF Alert", "aiwaf_events")
    assert ready["ready"] is True
