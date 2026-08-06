from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

from app.models.request import Catalog, CatalogField, CatalogTable, RequestContext
from app.models.response import ValidationIssue, ValidationResult


class CatalogAdapter(Protocol):
    """Future external catalog synchronizers must return this project model."""

    def fetch_catalog(self) -> Catalog: ...


class CatalogService:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Catalog | None:
        if not self.path.exists():
            return None
        return Catalog.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, catalog: Catalog) -> Catalog:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
        return catalog

    def resolve(self, context: RequestContext) -> Catalog | None:
        base_catalog = context.catalog or self.load()
        catalogs = [catalog for catalog in (base_catalog, context.request_catalog) if catalog and catalog.tables]
        if context.known_tables:
            catalogs.append(
                Catalog(
                    source="unknown",
                    tables=[
                        CatalogTable(table_name=name, fields=[CatalogField(field_name=field) for field in context.known_fields])
                        for name in context.known_tables
                    ],
                )
            )
        if not catalogs:
            return None
        return self._merge_catalogs(catalogs)

    @staticmethod
    def _merge_catalogs(catalogs: list[Catalog]) -> Catalog:
        tables: dict[str, CatalogTable] = {}
        for catalog in catalogs:
            for table in catalog.tables:
                existing = tables.get(table.table_name)
                if existing is None:
                    tables[table.table_name] = table.model_copy(deep=True)
                    continue
                existing_fields = {field.field_name for field in existing.fields}
                existing.fields.extend(
                    field.model_copy(deep=True) for field in table.fields if field.field_name not in existing_fields
                )
        primary = catalogs[0]
        return Catalog(
            tables=list(tables.values()),
            catalog_version=primary.catalog_version,
            updated_at=primary.updated_at,
            source=primary.source,
            function_type_rules=primary.function_type_rules,
        )

    def validate_query(self, query: str, context: RequestContext) -> ValidationResult:
        catalog = self.resolve(context)
        if catalog is None:
            return ValidationResult(valid=True, warnings=[ValidationIssue(
                code="catalog_unavailable", message="카탈로그가 없어 테이블과 필드의 실제 존재 여부를 확정 검증할 수 없습니다.",
                severity="warning", suggestion="카탈로그 fixture 또는 요청 context의 catalog를 제공하세요.", source="catalog",
            )], compatibility_notes=["Catalog validation is limited because no catalog was provided."])

        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        tables = self._tables(query)
        table_map = {table.table_name: table for table in catalog.tables}
        for table_name in tables:
            if table_name not in table_map and table_name != "YOUR_TABLE":
                errors.append(ValidationIssue(code="unknown_table", message=f"카탈로그에 '{table_name}' 테이블이 없습니다.", severity="error", affected_table=table_name, suggestion="테이블 이름 또는 카탈로그를 확인하세요.", source="catalog"))
        selected = [table_map[name] for name in tables if name in table_map]
        field_refs = self._field_refs(query)
        for field in field_refs:
            matches = [table for table in selected if any(item.field_name == field for item in table.fields)]
            if selected and not matches and field not in {"count", "_time"}:
                errors.append(ValidationIssue(code="unknown_field", message=f"선택한 테이블에서 '{field}' 필드를 찾을 수 없습니다.", severity="error", affected_field=field, suggestion="필드 이름 또는 카탈로그를 확인하세요.", source="catalog"))
            elif len(selected) > 1 and len(matches) > 1:
                warnings.append(ValidationIssue(code="ambiguous_field", message=f"'{field}' 필드가 여러 테이블에 있어 모호합니다.", severity="warning", affected_field=field, suggestion="테이블 또는 namespace를 명시하세요.", source="catalog"))
        for field, value in self._comparisons(query):
            definition = next((f for table in selected for f in table.fields if f.field_name == field), None)
            if definition and definition.field_type in {"number", "integer", "float"} and value.startswith(('"', "'")):
                errors.append(ValidationIssue(code="field_type_mismatch", message=f"숫자 필드 '{field}'에 문자열 비교가 사용되었습니다.", severity="error", affected_field=field, suggestion="숫자 값은 따옴표 없이 지정하세요.", source="catalog"))
        if "timechart" in query.lower() and catalog.source != "unknown" and selected:
            has_time_field = any(field.field_type.lower() in {"time", "datetime", "timestamp"} for table in selected for field in table.fields)
            if not has_time_field:
                warnings.append(ValidationIssue(code="time_field_unverified", message="선택한 테이블에서 시간 차트에 사용할 시간 타입 필드를 확인하지 못했습니다.", severity="warning", suggestion="카탈로그에 time/datetime/timestamp 타입 필드를 등록하세요.", source="catalog"))
        errors.extend(self._function_type_errors(query, selected, catalog))
        errors.extend(self._join_key_type_errors(query, selected))
        if context.request_catalog and context.request_catalog.tables:
            warnings.append(ValidationIssue(
                code="request_schema_unverified",
                message="요청에서 입력한 임시 스키마를 기준으로 생성했습니다. 실제 운영 카탈로그와의 일치 여부는 확인되지 않았습니다.",
                severity="warning",
                suggestion="운영 카탈로그를 등록하면 테이블별 필드와 타입을 더 엄격하게 검증할 수 있습니다.",
                source="catalog",
            ))
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings, compatibility_notes=[f"Catalog source: {catalog.source}"])

    @staticmethod
    def _tables(query: str) -> list[str]:
        tables: list[str] = []
        for line in query.splitlines():
            stripped = line.split("|", 1)[0].strip().lstrip("|").strip()
            if not stripped.lower().startswith("table "):
                continue
            candidates = [token.strip(",") for token in stripped.split()[1:] if "=" not in token]
            if candidates:
                tables.append(candidates[-1])
        for match in re.finditer(r"\btable\s+(?:[A-Za-z_][\w]*=\S+\s+)*([A-Za-z_][\w.]*)", query, flags=re.IGNORECASE):
            if match.group(1).lower() not in {"from", "to", "duration", "limit", "offset", "order"} and match.group(1) not in tables:
                tables.append(match.group(1))
        for match in re.finditer(r"\bfulltext\b[^\n|]*\bfrom\s+([^\n|]+)", query, flags=re.IGNORECASE):
            tables.extend(name.strip() for name in match.group(1).split(",") if re.fullmatch(r"[A-Za-z_][\w.]*", name.strip()))
        return tables

    @staticmethod
    def _field_refs(query: str) -> set[str]:
        import re
        fields: set[str] = set()
        for pattern in (r"\bfields\s+([^\n|]+)", r"\b(?:by|rename)\s+([A-Za-z_][\w]*)", r"\b(?:avg|sum|min|max|first|last)\(([A-Za-z_][\w]*)\)"):
            for value in re.findall(pattern, query):
                for token in re.findall(r"[A-Za-z_][\w]*", value):
                    if token not in {"as", "and", "or", "search", "fields", "by", "rename"}:
                        fields.add(token)
        fields.update(re.findall(r"\b([A-Za-z_][\w]*)\s*(?:==|!=|>=|<=|>|<)", query))
        fields.difference_update(re.findall(r"\bas\s+([A-Za-z_][\w]*)", query))
        return fields

    @staticmethod
    def _comparisons(query: str) -> list[tuple[str, str]]:
        import re
        return re.findall(r"\b([A-Za-z_][\w]*)\s*(?:==|!=|>=|<=|>|<)\s*(\"[^\"]*\"|'[^']*'|\S+)", query)

    @staticmethod
    def _function_type_errors(query: str, tables: list[CatalogTable], catalog: Catalog) -> list[ValidationIssue]:
        import re
        field_types = {field.field_name: field.field_type.lower() for table in tables for field in table.fields}
        errors: list[ValidationIssue] = []
        for rule in catalog.function_type_rules:
            for arguments in re.findall(rf"\b{re.escape(rule.function_name)}\(([^)]*)\)", query, flags=re.IGNORECASE):
                parts = [part.strip() for part in arguments.split(",")]
                if rule.argument_index >= len(parts):
                    continue
                field = parts[rule.argument_index]
                field_type = field_types.get(field)
                allowed = {value.lower() for value in rule.allowed_field_types}
                if field_type and field_type not in allowed:
                    errors.append(ValidationIssue(code="function_field_type_mismatch", message=f"{rule.function_name} 함수는 '{field}' 필드 타입({field_type})에 적용할 수 없습니다.", severity="error", affected_field=field, suggestion=f"허용 타입: {', '.join(rule.allowed_field_types)}", source="catalog"))
        return errors

    @staticmethod
    def _join_key_type_errors(query: str, tables: list[CatalogTable]) -> list[ValidationIssue]:
        if not re.search(r"\b(?:stream)?join\b", query, flags=re.IGNORECASE):
            return []
        helper_match = re.search(r"\b(?:stream)?join\s+(?:type=\w+\s+)?([A-Za-z_][\w]*)\s*\[", query, flags=re.IGNORECASE)
        if not helper_match:
            return []
        helper = helper_match.group(1)
        assignments = re.findall(rf"\beval\s+{re.escape(helper)}\s*=\s*([A-Za-z_][\w]*)", query, flags=re.IGNORECASE)
        if len(assignments) < 2 or len(tables) < 2:
            return []
        aliases = {target: source for source, target in re.findall(r"\brename\s+([A-Za-z_][\w]*)\s+as\s+([A-Za-z_][\w]*)", query, flags=re.IGNORECASE)}
        left_field = aliases.get(assignments[0], assignments[0])
        right_field = aliases.get(assignments[1], assignments[1])
        left_fields = {field.field_name: field.field_type.lower() for field in tables[0].fields}
        right_fields = {field.field_name: field.field_type.lower() for field in tables[1].fields}
        errors: list[ValidationIssue] = []
        if left_field not in left_fields:
            errors.append(ValidationIssue(code="join_key_not_in_left_table", message=f"왼쪽 조인 키 '{left_field}'가 '{tables[0].table_name}' 테이블에 없습니다.", severity="error", affected_table=tables[0].table_name, affected_field=left_field, suggestion="왼쪽 테이블의 조인 키를 확인하세요.", source="catalog"))
        if right_field not in right_fields:
            errors.append(ValidationIssue(code="join_key_not_in_right_table", message=f"오른쪽 조인 키 '{right_field}'가 '{tables[1].table_name}' 테이블에 없습니다.", severity="error", affected_table=tables[1].table_name, affected_field=right_field, suggestion="오른쪽 테이블의 조인 키를 확인하세요.", source="catalog"))
        if errors:
            return errors
        left = left_fields[left_field]
        right = right_fields[right_field]
        if left and right and left != "unknown" and right != "unknown" and left != right:
            return [ValidationIssue(code="join_key_type_mismatch", message=f"조인 키 타입이 일치하지 않습니다: {left} / {right}.", severity="error", affected_field=helper, suggestion="양쪽 조인 키의 타입이 같은지 카탈로그에서 확인하세요.", source="catalog")]
        return []
