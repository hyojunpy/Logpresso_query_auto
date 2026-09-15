from __future__ import annotations

import json
import re
from importlib.resources import files

from app.core.config import settings
from app.models.dashboard import (
    DashboardDefinition, DashboardDesignRequest, DashboardLayout, DashboardPanel,
    DashboardScope, DashboardThreshold, DashboardValidationResult,
)
from app.models.request import RequestContext
from app.services.catalog_service import CatalogService
from app.services.indexer import DocumentIndex
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever
from app.services.store_schema_knowledge import StoreSchemaKnowledge
from app.services.store_table_mapping import StoreTableMapping
from app.services.dashboard_operations import default_variables


PANEL_META = {
    "라이선스 만료일": ("status", "일", [
        DashboardThreshold(operator="<=", value=1, severity="critical", label="1일 이내 만료"),
        DashboardThreshold(operator="<=", value=7, severity="warning", label="7일 이내 만료"),
        DashboardThreshold(operator="<=", value=30, severity="info", label="30일 이내 만료"),
    ]),
    "일 로그 수집 현황": ("metric", "MB", []),
    "라이선스 종류": ("status", None, []),
    "수집 속도": ("metric", "EPS", [
        DashboardThreshold(operator="<=", value=0, severity="critical", label="수집 중단"),
    ]),
    "라이선스 사용 추이": ("line", "bytes", []),
    "최근 한 달 라이선스 초과 사용일": ("table", "GB", [
        DashboardThreshold(operator=">", value=100, severity="critical", label="계약 용량 초과"),
    ]),
    "최근 7일 라이선스 사용량 상위 수집기": ("bar", "bytes", []),
    "전일 수집기별 수집량": ("table", None, []),
}


PRODUCT_PANEL_RULES = [
    (("src_ip", "source_ip", "client_ip"), "출발지 IP 상위 10개", "출발지별 이벤트 분포", "bar"),
    (("dst_ip", "destination_ip", "server_ip"), "목적지 IP 상위 10개", "목적지별 이벤트 분포", "bar"),
    (("src_port", "source_port"), "출발지 포트 상위 10개", "출발지 포트별 이벤트 분포", "bar"),
    (("dst_port", "destination_port"), "목적지 포트 상위 10개", "목적지 포트별 이벤트 분포", "bar"),
    (("action", "act"), "처리 행위별 이벤트", "허용·차단 등 처리 행위 분포", "bar"),
    (("severity", "risk", "level", "priority"), "위험도별 이벤트", "심각도와 위험 수준별 이벤트 분포", "bar"),
    (("signature", "attack_name", "threat", "rule_name"), "탐지 유형 상위 10개", "시그니처·공격·위협 유형 분포", "bar"),
    (("user", "user_name", "username", "account"), "사용자 상위 10명", "사용자별 이벤트 분포", "bar"),
    (("hostname", "device_name", "host", "asset_name"), "장비/호스트 상위 10개", "장비 또는 호스트별 이벤트 분포", "bar"),
    (("category", "type", "log_type", "event_type"), "이벤트 유형별 현황", "범주와 이벤트 유형별 분포", "bar"),
    (("status", "result"), "처리 결과별 현황", "성공·실패 등 결과별 이벤트 분포", "bar"),
    (("protocol", "service"), "프로토콜/서비스별 현황", "프로토콜 또는 서비스별 분포", "bar"),
    (("policy", "policy_name", "rule"), "정책 상위 10개", "정책 또는 규칙별 이벤트 분포", "bar"),
    (("src_country", "source_country"), "출발지 국가 상위 10개", "출발지 국가별 이벤트 분포", "bar"),
    (("dst_country", "destination_country"), "목적지 국가 상위 10개", "목적지 국가별 이벤트 분포", "bar"),
]


class DashboardDesigner:
    def __init__(self):
        payload = json.loads(files("app.resources").joinpath("dashboard_query_examples.json").read_text(encoding="utf-8"))
        self.examples = payload.get("items", [])
        retriever = Retriever(DocumentIndex(settings.db_path))
        self.validator = QueryValidator(retriever)
        self.catalog = CatalogService(settings.catalog_path)

    def templates(self) -> list[dict]:
        return [
            {"id": "operations", "title": "Logpresso 운영 현황", "scope": "common", "panel_count": len(self.examples)},
            {"id": "product-security", "title": "제품별 보안 이벤트", "scope": "product", "panel_count": "dynamic"},
        ]

    def example_requests(self) -> list[dict]:
        return [{
            "id": "operations-all",
            "title": "통합 운영 현황",
            "description": "사용자가 제공한 운영 지표 8종을 한 화면에 구성합니다.",
            "request": "라이선스와 로그 수집 상태 운영 대시보드 만들어줘",
            "panel_count": len(self.examples),
        }, *[{
            "id": f"operations-{index + 1}",
            "title": item["title"],
            "description": item["description"],
            "request": f"{item['title']} 대시보드 만들어줘",
            "panel_count": 1,
        } for index, item in enumerate(self.examples)]]

    def product_example_catalog(self) -> list[dict]:
        knowledge = StoreSchemaKnowledge.active(settings.store_schema_path)
        rows = []
        for product in knowledge.payload.get("products", []):
            for schema in product.get("schemas", []):
                fields = [str(field.get("name")) for field in schema.get("fields", []) if field.get("name")]
                rows.append({
                    "manufacturer": product.get("manufacturer"),
                    "product": product.get("name"),
                    "schema": schema.get("name"),
                    "request": f"{product.get('name')} {schema.get('name')} 보안 대시보드 만들어줘",
                    "field_count": len(fields),
                    "coverage": "field-aware" if fields else "baseline",
                    "recommended_panels": self._recommended_product_panels(set(fields)),
                })
        return rows

    def design(self, request: DashboardDesignRequest) -> DashboardDefinition:
        if request.store_product:
            dashboard = self._product_dashboard(request)
        else:
            dashboard = self._operations_dashboard(request)
        return self.validate(dashboard, request.context)[0]

    def validate(
        self, dashboard: DashboardDefinition, context: RequestContext | None = None
    ) -> tuple[DashboardDefinition, DashboardValidationResult]:
        context = context or RequestContext()
        rows = []
        valid_count = 0
        for panel in dashboard.panels:
            syntax = self.validator.validate(panel.query)
            schema = self.catalog.validate_query(panel.query, context)
            syntax.errors.extend(schema.errors)
            syntax.warnings.extend(schema.warnings)
            syntax.valid = not syntax.errors
            panel.validation = syntax
            valid_count += int(syntax.valid)
            rows.append({
                "id": panel.id, "title": panel.title, "valid": syntax.valid,
                "errors": [issue.message for issue in syntax.errors],
                "warnings": [issue.message for issue in syntax.warnings],
            })
        result = DashboardValidationResult(
            valid=valid_count == len(dashboard.panels), panel_count=len(dashboard.panels),
            valid_panels=valid_count, invalid_panels=len(dashboard.panels) - valid_count, panels=rows,
        )
        return dashboard, result

    def _operations_dashboard(self, request: DashboardDesignRequest) -> DashboardDefinition:
        selected = self._select_examples(request.request)
        panels = []
        for index, example in enumerate(selected):
            visualization, unit, thresholds = PANEL_META[example["title"]]
            panels.append(DashboardPanel(
                id=f"operations-{index + 1}", title=example["title"], description=example["description"],
                visualization=visualization, query=example["query"], unit=unit, thresholds=thresholds,
                layout=self._layout(index),
            ))
        return DashboardDefinition(
            title="Logpresso 운영 현황", description="라이선스와 로그 수집 상태를 한 화면에서 확인합니다.",
            default_time_range=request.default_time_range,
            refresh_interval_seconds=request.refresh_interval_seconds,
            variables=default_variables(request.default_time_range), panels=panels,
        )

    def _product_dashboard(self, request: DashboardDesignRequest) -> DashboardDefinition:
        knowledge = StoreSchemaKnowledge.active(settings.store_schema_path)
        product = next((item for item in knowledge.payload.get("products", []) if item.get("name") == request.store_product), None)
        schema = next((item for item in (product or {}).get("schemas", []) if item.get("name") == request.store_schema), None)
        fields = {str(field.get("name")) for field in (schema or {}).get("fields", [])}
        table = request.table_name or StoreTableMapping(settings.store_table_mapping_path).resolve(
            request.store_product, request.store_schema
        ) or "secui_events"
        duration = request.default_time_range
        base_query = f"table duration={duration} {table}"
        queries = [("전체 이벤트", "전체 이벤트 건수", "metric", f"{base_query}\n| stats count", "건")]
        if "_time" in fields:
            queries.append(("이벤트 시간 추이", "시간대별 이벤트 발생 추이", "line", f"{base_query}\n| timechart span=1h count", "건"))
        for candidates, title, description, visual in PRODUCT_PANEL_RULES:
            field = next((candidate for candidate in candidates if candidate in fields), None)
            if field:
                queries.append((title, description, visual, f"{base_query}\n| stats count by {field}\n| sort -count\n| limit 10", "건"))
        volume_field = next((field for field in ("total_bytes", "bytes", "sent_bytes", "recv_bytes", "volume") if field in fields), None)
        if volume_field:
            queries.append(("트래픽 사용량 상위 10개", f"{volume_field} 합계가 큰 항목을 확인합니다.", "bar", f"{base_query}\n| stats sum({volume_field}) as volume by src_ip\n| sort -volume\n| limit 10" if "src_ip" in fields else f"{base_query}\n| stats sum({volume_field}) as volume", "bytes"))
        queries.append(("최근 이벤트", "최근 수집된 Syslog 이벤트를 표로 확인합니다.", "table", f"{base_query}\n| limit 100", None))
        if schema and schema.get("discriminator_field") and schema.get("log_types"):
            field = schema["discriminator_field"]
            values = " or ".join(f'{field} == "{value}"' for value in schema["log_types"])
            queries = [(title, description, visual, query.replace("\n|", f"\n| search {values}\n|", 1), unit) for title, description, visual, query, unit in queries]
        panels = [DashboardPanel(
            id=f"product-{index + 1}", title=title, description=description,
            visualization=visual, query=query, unit=unit, layout=self._layout(index),
        ) for index, (title, description, visual, query, unit) in enumerate(queries)]
        return DashboardDefinition(
            title=f"{request.store_product} 대시보드",
            description=f"{request.store_schema or request.store_product}의 주요 보안 이벤트를 모니터링합니다.",
            default_time_range=duration, refresh_interval_seconds=request.refresh_interval_seconds,
            scope=DashboardScope(manufacturer=request.manufacturer, product=request.store_product, schema_name=request.store_schema),
            variables=default_variables(duration), panels=panels,
        )

    @staticmethod
    def _recommended_product_panels(fields: set[str]) -> list[str]:
        panels = ["전체 이벤트"]
        if "_time" in fields:
            panels.append("이벤트 시간 추이")
        for candidates, title, _, _ in PRODUCT_PANEL_RULES:
            if any(field in fields for field in candidates):
                panels.append(title)
        if any(field in fields for field in ("total_bytes", "bytes", "sent_bytes", "recv_bytes", "volume")):
            panels.append("트래픽 사용량 상위 10개")
        panels.append("최근 이벤트")
        return panels

    def _select_examples(self, request: str) -> list[dict]:
        normalized = re.sub(r"\s+", "", request.casefold())
        selected = []
        for item in self.examples:
            phrases = [item["title"], *item.get("aliases", [])]
            if any(re.sub(r"\s+", "", phrase.casefold()) in normalized for phrase in phrases):
                selected.append(item)
        if selected:
            return selected
        if "라이선스" in request and "수집" not in request:
            return [item for item in self.examples if "라이선스" in item["title"]]
        if "수집" in request and "라이선스" not in request:
            return [item for item in self.examples if "수집" in item["title"] or "수집기" in item["title"]]
        return self.examples

    @staticmethod
    def _layout(index: int) -> DashboardLayout:
        return DashboardLayout(x=(index % 2) * 6, y=(index // 2) * 4, width=6, height=4)


def dashboard_to_yaml(dashboard: DashboardDefinition) -> str:
    """Emit portable YAML without adding a runtime dependency."""
    def scalar(value):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(str(value), ensure_ascii=False)

    def render(value, indent=0):
        prefix = " " * indent
        lines = []
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(render(child, indent + 2))
                else:
                    lines.append(f"{prefix}{key}: {scalar(child)}")
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    lines.append(f"{prefix}-")
                    lines.extend(render(child, indent + 2))
                else:
                    lines.append(f"{prefix}- {scalar(child)}")
        return lines
    return "\n".join(render(dashboard.model_dump(exclude_none=True))) + "\n"
