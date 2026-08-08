import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models.request import Catalog, GenerateQueryRequest, RequestContext
from app.services.catalog_service import CatalogService
from app.services.execution_preview import ExecutionPreviewService
from app.services.quality_analyzer import QueryQualityAnalyzer
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever
from app.services.query_generator import QueryGenerator
from tests.support import shared_index


def test_catalog_detects_unknown_table_field_and_type():
    catalog = Catalog.model_validate({"source": "fixture", "tables": [{"table_name": "logs", "fields": [{"field_name": "bytes", "field_type": "number"}]}]})
    service = CatalogService(Path("data") / "does-not-exist-catalog.json")
    result = service.validate_query('table logs | search bytes == "large"', RequestContext(catalog=catalog))
    assert not result.valid
    assert "field_type_mismatch" in {item.code for item in result.errors}
    result = service.validate_query("table missing", RequestContext(catalog=catalog))
    assert "unknown_table" in {item.code for item in result.errors}


def test_request_catalog_extends_validation_without_persisting_schema():
    persisted_catalog = Catalog.model_validate({
        "source": "fixture",
        "tables": [{"table_name": "firewall_logs", "fields": [{"field_name": "src_ip", "field_type": "ip"}]}],
    })
    request_catalog = Catalog.model_validate({
        "source": "unknown",
        "tables": [{"table_name": "custom_logs", "fields": [{"field_name": "client_id", "field_type": "unknown"}]}],
    })
    result = CatalogService(Path("data") / "does-not-exist-catalog.json").validate_query(
        "table custom_logs | fields client_id",
        RequestContext(catalog=persisted_catalog, request_catalog=request_catalog),
    )
    assert result.valid
    assert "request_schema_unverified" in {item.code for item in result.warnings}
    assert "unknown_table" not in {item.code for item in result.errors}
    assert "unknown_field" not in {item.code for item in result.errors}


def test_catalog_service_persists_manually_edited_fields():
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        service = CatalogService(Path(tmp) / "catalog.json")
        catalog = Catalog.model_validate(
            {
                "source": "manual",
                "tables": [
                    {
                        "table_name": "custom_logs",
                        "fields": [
                            {"field_name": "client_id", "field_type": "string", "description": "request client"},
                            {"field_name": "bytes", "field_type": "number"},
                        ],
                    }
                ],
            }
        )
        service.save(catalog)
        loaded = service.load()
    assert loaded is not None
    assert loaded.source == "manual"
    assert [(field.field_name, field.field_type) for field in loaded.tables[0].fields] == [
        ("client_id", "string"),
        ("bytes", "number"),
    ]


def test_catalog_function_type_rule_and_timechart_warning():
    catalog = Catalog.model_validate({
        "source": "fixture",
        "function_type_rules": [{"function_name": "fixture_ip_check", "allowed_field_types": ["ip"]}],
        "tables": [{"table_name": "logs", "fields": [{"field_name": "message", "field_type": "string"}]}],
    })
    service = CatalogService(Path("data") / "does-not-exist-catalog.json")
    result = service.validate_query("table logs | stats fixture_ip_check(message)", RequestContext(catalog=catalog))
    assert "function_field_type_mismatch" in {item.code for item in result.errors}
    result = service.validate_query("table logs | timechart count", RequestContext(catalog=catalog))
    assert "time_field_unverified" in {item.code for item in result.warnings}


def test_catalog_detects_ambiguous_field_across_fulltext_tables():
    catalog = Catalog.model_validate({"source": "fixture", "tables": [
        {"table_name": "web_logs", "fields": [{"field_name": "host", "field_type": "string"}]},
        {"table_name": "app_logs", "fields": [{"field_name": "host", "field_type": "string"}]},
    ]})
    result = CatalogService(Path("data") / "does-not-exist-catalog.json").validate_query(
        'fulltext duration=1h "timeout" from web_logs, app_logs | fields host', RequestContext(catalog=catalog)
    )
    assert "ambiguous_field" in {item.code for item in result.warnings}


def test_catalog_detects_join_key_type_mismatch_and_quality_warns():
    catalog = Catalog.model_validate({"source": "fixture", "tables": [
        {"table_name": "left_logs", "fields": [{"field_name": "src_ip", "field_type": "ip"}]},
        {"table_name": "right_logs", "fields": [{"field_name": "dst_ip", "field_type": "string"}]},
    ]})
    query = "table left_logs | eval _join_key = src_ip | join type=left _join_key [ table right_logs | eval _join_key = dst_ip ]"
    schema = CatalogService(Path("data") / "does-not-exist-catalog.json").validate_query(query, RequestContext(catalog=catalog))
    assert "join_key_type_mismatch" in {item.code for item in schema.errors}
    quality = QueryQualityAnalyzer().analyze(query, QueryValidator(Retriever(shared_index())).validate(query))
    assert "unbounded_join" in {item.code for item in quality.diagnostics}


def test_catalog_detects_join_key_on_wrong_table_side():
    catalog = Catalog.model_validate({"source": "fixture", "tables": [
        {"table_name": "left_logs", "fields": [{"field_name": "left_id", "field_type": "string"}]},
        {"table_name": "right_logs", "fields": [{"field_name": "right_id", "field_type": "string"}]},
    ]})
    query = "table left_logs | eval _join_key = right_id | join type=left _join_key [ table right_logs | eval _join_key = left_id ]"
    result = CatalogService(Path("data") / "does-not-exist-catalog.json").validate_query(query, RequestContext(catalog=catalog))
    assert {"join_key_not_in_left_table", "join_key_not_in_right_table"}.issubset({item.code for item in result.errors})


def test_quality_and_preview_do_not_execute_external_queries():
    validator = QueryValidator(Retriever(shared_index()))
    validation = validator.validate('table firewall_logs | search status == 200 | search status == 500')
    quality = QueryQualityAnalyzer().analyze('table firewall_logs | search status == 200 | search status == 500', validation)
    assert quality.risk_level in {"high", "critical"}
    assert "contradictory_filter" in {item.code for item in quality.diagnostics}
    preview = ExecutionPreviewService().build('table firewall_logs', validation, quality)
    assert preview.status in {"requires_confirmation", "blocked"}
    assert preview.is_read_only is True


def test_quality_detects_contradictory_numeric_range():
    validation = QueryValidator(Retriever(shared_index())).validate("table logs | search bytes > 1000 | search bytes < 10")
    quality = QueryQualityAnalyzer().analyze("table logs | search bytes > 1000 | search bytes < 10", validation)
    assert "contradictory_range" in {item.code for item in quality.diagnostics}


def test_quality_warns_about_unfiltered_aggregation():
    query = "table firewall_logs | stats count by src_ip"
    quality = QueryQualityAnalyzer().analyze(query, QueryValidator(Retriever(shared_index())).validate(query))
    assert "aggregation_without_pre_filter" in {item.code for item in quality.diagnostics}


def test_quality_reports_fulltext_join_and_limit_score_reasons():
    validator = QueryValidator(Retriever(shared_index()))
    fulltext = QueryQualityAnalyzer().analyze('fulltext "timeout"', validator.validate('fulltext "timeout"'))
    fulltext_codes = {item.code for item in fulltext.diagnostics}
    assert {"broad_fulltext", "fulltext_without_time_range", "missing_result_limit"}.issubset(fulltext_codes)
    assert "fulltext_without_time_range" in fulltext.score_reasons["performance_score"]

    join = QueryQualityAnalyzer().analyze(
        "table left_logs | join type=left key [ table right_logs ] | limit 20000",
        validator.validate("table left_logs | join type=left key [ table right_logs ] | limit 20000"),
    )
    join_codes = {item.code for item in join.diagnostics}
    assert {"missing_time_range", "join_without_pre_filter", "excessive_result_limit"}.issubset(join_codes)
    assert "excessive_result_limit" in join.score_reasons["performance_score"]

    unbounded_join = QueryQualityAnalyzer().analyze(
        "table left_logs | join type=left key [ table right_logs ]",
        validator.validate("table left_logs | join type=left key [ table right_logs ]"),
    )
    assert "unbounded_join" in {item.code for item in unbounded_join.diagnostics}


def test_quality_warns_about_timechart_span_and_bucket_count():
    validator = QueryValidator(Retriever(shared_index()))
    missing_span = QueryQualityAnalyzer().analyze("table duration=24h logs | timechart count", validator.validate("table duration=24h logs | timechart count"))
    assert "timechart_span_unspecified" in {item.code for item in missing_span.diagnostics}
    dense = QueryQualityAnalyzer().analyze("table duration=30d logs | timechart span=1s count", validator.validate("table duration=30d logs | timechart span=1s count"))
    assert "timechart_excessive_buckets" in {item.code for item in dense.diagnostics}


def test_clarification_has_not_requested_execution_preview():
    response = QueryGenerator(Retriever(shared_index())).generate(
        GenerateQueryRequest(request="에러 로그 보여줘", context=RequestContext())
    )
    assert response.status == "needs_clarification"
    assert response.execution_preview.status == "not_requested"


def test_feedback_api_masks_secrets_and_catalog_api_roundtrip():
    from app.api.main import app
    from app.core.config import settings
    from fastapi.testclient import TestClient
    original_catalog_path = settings.catalog_path
    original_db_path = settings.db_path
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings.catalog_path = Path(tmp) / "catalog.json"
        settings.db_path = Path(tmp) / "app.db"
        client = TestClient(app)
        response = client.put("/api/v1/catalog", json={"catalog": {"source": "fixture", "tables": [{"table_name": "logs", "fields": []}]}})
        assert response.status_code == 200
        assert client.get("/api/v1/catalog").json()["tables"][0]["table_name"] == "logs"
        saved = client.post("/api/v1/feedback", json={"request_text": "token=secret", "result_status": "generated", "rating": "negative", "feedback_comment": "password=secret"})
        assert saved.status_code == 200 and saved.json()["raw_text_stored"] is False
    settings.catalog_path = original_catalog_path
    settings.db_path = original_db_path


def test_catalog_csv_import_api_validates_and_persists_fixture():
    from app.api.main import app
    from app.core.config import settings
    from fastapi.testclient import TestClient

    original_catalog_path = settings.catalog_path
    original_db_path = settings.db_path
    try:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            settings.catalog_path = Path(tmp) / "catalog.json"
            settings.db_path = Path(tmp) / "app.db"
            client = TestClient(app)
            response = client.post(
                "/api/v1/catalog/import/csv",
                content="table_name,field_name,field_type,description\nfirewall,src_ip,ip,source\n",
                headers={"content-type": "text/csv", "X-Actor-ID": "catalog-admin"},
            )
            assert response.status_code == 200
            assert response.json()["tables"][0]["fields"][0]["field_name"] == "src_ip"
            invalid = client.post(
                "/api/v1/catalog/import/csv",
                content="table_name,field_name\nfirewall,src_ip\n",
                headers={"content-type": "text/csv"},
            )
            assert invalid.status_code == 422
            assert invalid.json()["detail"]["code"] == "invalid_catalog_csv"
            audit = client.get("/api/v1/internal/audit").json()["items"]
            assert audit[0]["action"] == "catalog.import_csv"
            assert audit[0]["actor"] == "catalog-admin"
    finally:
        settings.catalog_path = original_catalog_path
        settings.db_path = original_db_path


def test_catalog_csv_export_api_returns_utf8_csv():
    from app.api.main import app
    from app.core.config import settings
    from fastapi.testclient import TestClient

    original_catalog_path = settings.catalog_path
    original_db_path = settings.db_path
    try:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            settings.catalog_path = Path(tmp) / "catalog.json"
            settings.db_path = Path(tmp) / "app.db"
            client = TestClient(app)
            client.put("/api/v1/catalog", json={"catalog": {"source": "fixture", "tables": [{
                "table_name": "firewall", "node": "node-a", "namespace": "security", "description": "Firewall events", "fields": [{"field_name": "src_ip", "field_type": "ip", "nullable": False}],
            }]}})
            response = client.get("/api/v1/catalog/export/csv")
    finally:
        settings.catalog_path = original_catalog_path
        settings.db_path = original_db_path

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("\ufefftable_name,node,namespace,table_description,field_name,field_type,nullable,description")
    assert "firewall,node-a,security,Firewall events,src_ip,ip,false," in response.text


def test_gold_set_api_is_disabled_by_default():
    from app.api.main import app
    from app.core.config import settings
    from fastapi.testclient import TestClient
    original = settings.enable_dev_evaluation
    settings.enable_dev_evaluation = False
    try:
        assert TestClient(app).post("/api/v1/internal/evaluations/gold-set").status_code == 404
    finally:
        settings.enable_dev_evaluation = original


def test_feedback_summary_does_not_return_raw_text():
    from app.api.main import app
    from fastapi.testclient import TestClient
    body = TestClient(app).get("/api/v1/feedback/summary").json()
    assert {"total", "ratings", "issue_types", "unresolved_outcomes"}.issubset(body)
    assert "request_text" not in body and "generated_query" not in body


def test_feedback_improvement_report_returns_only_aggregated_metadata():
    from app.api.main import app
    from app.core.config import settings
    from fastapi.testclient import TestClient

    original = settings.db_path
    try:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            settings.db_path = Path(tmp) / "feedback.db"
            client = TestClient(app)
            saved = client.post("/api/v1/feedback", json={
                "request_text": "token=secret", "generated_query": "table confidential_logs",
                "result_status": "generated", "rating": "negative", "issue_type": "wrong_field",
            })
            assert saved.status_code == 200
            body = client.get("/api/v1/feedback/improvement-report").json()
    finally:
        settings.db_path = original

    assert body["total_feedback"] == 1
    assert body["issue_types"] == {"wrong_field": 1}
    assert body["priority_issue_types"] == ["wrong_field"]
    assert "token=secret" not in str(body)
    assert "confidential_logs" not in str(body)


def test_query_analysis_api_returns_quality_and_preview():
    from app.api.main import app
    from fastapi.testclient import TestClient
    response = TestClient(app).post("/api/v1/query/analyze", json={"query": "table firewall_logs"})
    body = response.json()
    assert response.status_code == 200
    assert {"validation", "schema_validation", "quality", "execution_preview"}.issubset(body)
    assert body["quality"]["risk_level"] in {"low", "medium", "high", "critical"}


def test_validate_api_uses_legacy_context_for_schema_validation():
    from app.api.main import app
    from fastapi.testclient import TestClient
    body = TestClient(app).post("/api/v1/query/validate", json={
        "query": "table firewall_logs | search missing_field == 1",
        "context": {"known_tables": ["firewall_logs"], "known_fields": ["src_ip"]},
    }).json()
    assert "unknown_field" in {item["code"] for item in body["errors"]}


def test_gold_set_has_ten_cases_and_declares_semantic_assertions():
    cases = json.loads((Path("tests") / "fixtures" / "gold_set.json").read_text(encoding="utf-8"))
    assert len(cases) >= 10
    assert all("expected_status" in case and "forbidden" in case for case in cases)


def test_gold_set_executes_semantic_checks():
    cases = json.loads((Path("tests") / "fixtures" / "gold_set.json").read_text(encoding="utf-8"))
    generator = QueryGenerator(Retriever(shared_index()))
    status_map = {"success": "generated", "clarification": "needs_clarification", "unsupported": "unsupported"}
    for case in cases:
        catalog = Catalog.model_validate(case["catalog"])
        context = RequestContext(
            catalog=catalog,
            known_tables=case.get("known_tables", [table.table_name for table in catalog.tables]),
            known_fields=case.get("known_fields", [field.field_name for table in catalog.tables for field in table.fields]),
            known_loggers=case.get("known_loggers", []),
            known_streams=case.get("known_streams", []),
        )
        response = generator.generate(GenerateQueryRequest(request=case["request"], context=context))
        assert response.status == status_map[case["expected_status"]], case["request"]
        if response.query:
            assert all(keyword in response.query for keyword in case["keywords"]), case["request"]
        codes = {item.code for item in (response.quality.diagnostics if response.quality else [])}
        assert set(case["warning_codes"]).issubset(codes)
        assert not (set(case["forbidden"]) & codes)
