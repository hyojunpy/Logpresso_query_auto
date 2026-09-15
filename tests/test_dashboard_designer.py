import json

from app.models.dashboard import DashboardDesignRequest
from app.services.dashboard_designer import DashboardDesigner, dashboard_to_yaml


def test_builds_eight_panel_operations_dashboard_with_visuals_and_thresholds():
    dashboard = DashboardDesigner().design(DashboardDesignRequest(
        request="라이선스와 로그 수집 상태 운영 대시보드 만들어줘"
    ))
    assert len(dashboard.panels) == 8
    assert all(panel.validation and panel.validation.valid for panel in dashboard.panels)
    assert {panel.visualization for panel in dashboard.panels} >= {"metric", "status", "line", "bar", "table"}
    assert next(panel for panel in dashboard.panels if panel.title == "라이선스 만료일").thresholds


def test_natural_language_selects_only_requested_dashboard_panel():
    dashboard = DashboardDesigner().design(DashboardDesignRequest(request="수집 속도 대시보드 만들어줘"))
    assert [panel.title for panel in dashboard.panels] == ["수집 속도"]


def test_product_dashboard_uses_available_schema_fields():
    dashboard = DashboardDesigner().design(DashboardDesignRequest(
        request="AIWAF 보안 이벤트 대시보드 만들어줘", manufacturer="MONITORAPP",
        store_product="AIWAF", store_schema="AIWAF Alert", table_name="aiwaf_events",
    ))
    assert dashboard.scope.product == "AIWAF"
    assert any("src_ip" in panel.query for panel in dashboard.panels)
    assert all("aiwaf_events" in panel.query for panel in dashboard.panels)


def test_dashboard_exports_are_portable_json_and_yaml():
    dashboard = DashboardDesigner().design(DashboardDesignRequest(request="수집 속도"))
    assert json.loads(dashboard.model_dump_json())["panels"][0]["title"] == "수집 속도"
    yaml = dashboard_to_yaml(dashboard)
    assert 'title: "Logpresso 운영 현황"' in yaml
    assert "panels:" in yaml


def test_user_supplied_dashboard_examples_are_exposed_as_presets():
    examples = DashboardDesigner().example_requests()
    assert len(examples) == 9
    assert examples[0]["panel_count"] == 8
    assert {item["title"] for item in examples[1:]} >= {"라이선스 만료일", "수집 속도", "전일 수집기별 수집량"}
