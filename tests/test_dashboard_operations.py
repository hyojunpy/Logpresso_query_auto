from app.models.dashboard import DashboardDefinition, DashboardLayout, DashboardPanel, LogpressoTarget
from app.services.dashboard_operations import PRODUCT_TEMPLATES, analyze_dashboard, default_variables, deployment_plan


def dashboard():
    return DashboardDefinition(
        title="운영", description="운영 현황", refresh_interval_seconds=30,
        variables=default_variables("24h"), panels=[DashboardPanel(
            id="table", title="상세", description="상세", visualization="table",
            query="table duration=30d events | join src_ip [table assets] | stats count by src_ip | sort -count",
            layout=DashboardLayout(x=0, y=0, width=12, height=4),
        )],
    )


def test_product_categories_and_performance_analysis():
    assert {item["id"] for item in PRODUCT_TEMPLATES} >= {"firewall", "waf", "ips", "vpn", "nac", "edr"}
    result = analyze_dashboard(dashboard())
    assert result.estimated_query_weight > 5
    assert result.score < 100
    assert any("limit" in item for item in result.recommendations)


def test_deployment_plan_is_tls_safe_and_maps_widgets():
    safe = deployment_plan(dashboard(), LogpressoTarget(base_url="https://10.11.12.14", verify_tls=True))
    assert safe.compatible is True
    assert safe.widget_count == 1
    assert safe.variable_count == 2
    assert safe.payload["widgets"][0]["query"].startswith("table")

    unsafe = deployment_plan(dashboard(), LogpressoTarget(base_url="https://10.11.12.14", verify_tls=False))
    assert unsafe.compatible is False
    assert any("TLS" in item for item in unsafe.warnings)
