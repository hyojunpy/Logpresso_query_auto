from __future__ import annotations

import re

from app.models.dashboard import DashboardAnalysis, DashboardDefinition, DashboardDeploymentPlan, DashboardVariable, LogpressoTarget


PRODUCT_TEMPLATES = [
    {"id": "firewall", "title": "방화벽 위협/트래픽", "keywords": ["FW", "NGFW", "방화벽", "AXGATE"], "recommended_fields": ["src_ip", "dst_ip", "action", "protocol"]},
    {"id": "waf", "title": "웹 공격/차단", "keywords": ["WAF", "웹방화벽", "AIWAF"], "recommended_fields": ["src_ip", "url", "action", "severity"]},
    {"id": "ips", "title": "침입 탐지/차단", "keywords": ["IPS", "IDS"], "recommended_fields": ["src_ip", "signature", "action", "severity"]},
    {"id": "vpn", "title": "VPN 접속/실패", "keywords": ["VPN", "SSLVPN"], "recommended_fields": ["user", "src_ip", "status", "duration"]},
    {"id": "nac", "title": "단말 접속/격리", "keywords": ["NAC"], "recommended_fields": ["user", "ip", "mac", "status"]},
    {"id": "edr", "title": "엔드포인트 위협", "keywords": ["EDR", "EPP"], "recommended_fields": ["hostname", "user", "threat", "severity"]},
]


def default_variables(time_range: str) -> list[DashboardVariable]:
    return [
        DashboardVariable(name="time_range", label="조회 기간", kind="time_range", default=time_range, required=True),
        DashboardVariable(name="asset", label="자산/수집기", kind="text", default=""),
    ]


def analyze_dashboard(dashboard: DashboardDefinition) -> DashboardAnalysis:
    warnings, recommendations, details = [], [], []
    total = 0
    for panel in dashboard.panels:
        weight = 1
        reasons = []
        query = panel.query.casefold()
        for pattern, cost, label in ((r"\bjoin\b", 4, "join"), (r"\btimechart\b", 2, "timechart"), (r"\bstats\b", 2, "stats"), (r"\bsort\b", 1, "sort"), (r"duration=(?:30d|90d|\d+y)", 4, "long range")):
            if re.search(pattern, query):
                weight += cost
                reasons.append(label)
        if "limit " not in query and panel.visualization == "table":
            warnings.append(f"{panel.title}: 테이블 결과 제한이 없습니다.")
            recommendations.append(f"{panel.title}: 적절한 limit을 추가하세요.")
            weight += 2
        total += weight
        details.append({"panel_id": panel.id, "weight": weight, "reasons": reasons})
    if len(dashboard.panels) > 8:
        warnings.append("동시 실행 패널이 8개를 초과합니다.")
        recommendations.append("새로고침 주기를 늘리거나 대시보드를 분리하세요.")
    if dashboard.refresh_interval_seconds < 60:
        warnings.append("새로고침 주기가 60초 미만입니다.")
    score = max(0, 100 - total * 2 - len(warnings) * 5)
    return DashboardAnalysis(score=score, estimated_query_weight=total, warnings=warnings, recommendations=list(dict.fromkeys(recommendations)), panel_details=details)


def deployment_plan(dashboard: DashboardDefinition, target: LogpressoTarget) -> DashboardDeploymentPlan:
    warnings = []
    if target.base_url.startswith("https://") and not target.verify_tls:
        warnings.append("TLS 인증서 검증이 비활성화되어 실제 배포는 차단됩니다.")
    payload = {
        "name": dashboard.title,
        "description": dashboard.description,
        "variables": [item.model_dump() for item in dashboard.variables],
        "widgets": [{"name": panel.title, "type": panel.visualization, "query": panel.query, "layout": panel.layout.model_dump(), "unit": panel.unit} for panel in dashboard.panels],
    }
    return DashboardDeploymentPlan(
        target=target, compatible=target.verify_tls and bool(dashboard.panels), dashboard_title=dashboard.title,
        variable_count=len(dashboard.variables), widget_count=len(dashboard.panels),
        steps=["대상 버전 및 권한 확인", "사용자 정의 변수 생성", "대시보드 생성", "위젯 및 쿼리 등록", "레이아웃 적용", "조회 결과 검증"],
        warnings=warnings + ["Logpresso 버전별 API 계약 확인 전에는 실제 배포를 수행하지 않습니다."], payload=payload,
    )
