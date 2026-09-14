from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import re
from typing import Any

from app.models.request import Catalog, CatalogField, CatalogTable, GenerateQueryRequest


@dataclass(frozen=True)
class SecuiMatch:
    product: str | None
    schema_name: str | None
    log_type: str | None
    schema_aliases: tuple[str, ...]
    fields: tuple[dict[str, Any], ...]
    replacements: tuple[tuple[str, str], ...]


class SecuiKnowledge:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> "SecuiKnowledge":
        resource = files("app.resources").joinpath("secui_schema.json")
        return cls(json.loads(resource.read_text(encoding="utf-8")))

    def match(self, text: str) -> SecuiMatch | None:
        products = self.payload.get("products", [])
        product_matches = [
            product for product in products
            if any(self._contains(text, alias) for alias in product.get("aliases", []))
        ]
        if len(product_matches) > 1:
            return None
        product = product_matches[0] if product_matches else None
        schemas = product.get("schemas", []) if product else [schema for item in products for schema in item.get("schemas", [])]
        matched = self._matching_schemas(text, schemas, include_log_types=product is not None)
        if not matched and not product:
            return None
        active_schemas = matched or schemas
        log_types = {log_type for schema in matched for log_type in schema.get("log_types", [])}
        log_type = next(iter(log_types)) if len(log_types) == 1 else None
        fields = self._unique_fields(active_schemas)
        replacements = self._field_replacements(text, fields)
        return SecuiMatch(
            product=product.get("name") if product else None,
            schema_name=matched[0].get("name") if len(matched) == 1 else None,
            log_type=log_type,
            schema_aliases=tuple(matched[0].get("aliases", [])) if len(matched) == 1 else (),
            fields=tuple(fields),
            replacements=tuple(replacements),
        )

    def enrich(self, payload: GenerateQueryRequest) -> GenerateQueryRequest:
        match = self.match(payload.request)
        if match is None:
            return payload
        context = payload.context.model_copy(deep=True)
        request = payload.request
        if match.schema_name:
            for alias in sorted(match.schema_aliases, key=len, reverse=True):
                if alias != match.schema_name and self._contains(request, alias):
                    request = re.sub(re.escape(alias), match.schema_name, request, count=1, flags=re.IGNORECASE)
                    break
        for phrase, field_name in match.replacements:
            request = re.sub(re.escape(phrase), field_name, request, flags=re.IGNORECASE)
        known_fields = [field["name"] for field in match.fields]
        if match.log_type:
            known_fields.append("log_type")
        context.known_fields = list(dict.fromkeys([*context.known_fields, *known_fields]))
        if match.product and not context.product:
            context.product = match.product
        if len(context.known_tables) == 1 and match.fields and context.request_catalog is None:
            context.request_catalog = Catalog(
                source="external_sync",
                catalog_version=str(self.payload.get("version") or "unknown"),
                tables=[
                    CatalogTable(
                        table_name=context.known_tables[0],
                        description=f"{match.product or 'SECUI'} {match.schema_name or 'schema'}",
                        fields=[
                            CatalogField(
                                field_name=field["name"],
                                field_type=field["type"],
                                description=field.get("display_name") or field.get("description") or None,
                            )
                            for field in match.fields
                        ] + ([CatalogField(field_name="log_type", field_type="string", description="로그 유형")] if match.log_type else []),
                    )
                ],
            )
        return payload.model_copy(update={"request": request, "context": context})

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        if phrase.isascii() and re.fullmatch(r"[A-Za-z0-9_-]+", phrase):
            return bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(phrase)}(?![A-Za-z0-9_-])", text, flags=re.IGNORECASE))
        return phrase.lower() in text.lower()

    def _matching_schemas(
        self, text: str, schemas: list[dict[str, Any]], *, include_log_types: bool
    ) -> list[dict[str, Any]]:
        scored: list[tuple[int, dict[str, Any]]] = []
        for schema in schemas:
            phrases = list(schema.get("aliases", []))
            if include_log_types:
                phrases = [*schema.get("log_types", []), *phrases]
            lengths = [len(phrase) for phrase in phrases if len(phrase) >= 2 and self._contains(text, phrase)]
            if lengths:
                scored.append((max(lengths), schema))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        return [schema for score, schema in scored if score == best]

    @staticmethod
    def _unique_fields(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        for schema in schemas:
            for field in schema.get("fields", []):
                fields.setdefault(field["name"], field)
        return list(fields.values())

    def _field_replacements(self, text: str, fields: list[dict[str, Any]]) -> list[tuple[str, str]]:
        aliases: dict[str, set[str]] = {}
        for field in fields:
            for alias in field.get("aliases", []):
                if self._field_alias_match(text, alias):
                    aliases.setdefault(alias, set()).add(field["name"])
        replacements = [
            (alias, next(iter(names))) for alias, names in aliases.items() if len(names) == 1
        ]
        replacements.sort(key=lambda item: len(item[0]), reverse=True)
        accepted: list[tuple[str, str]] = []
        occupied: list[tuple[int, int]] = []
        for alias, target in replacements:
            match = self._field_alias_match(text, alias)
            if not match or any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            occupied.append(match.span())
            accepted.append((alias, target))
        return accepted

    @staticmethod
    def _field_alias_match(text: str, alias: str) -> re.Match[str] | None:
        # Do not turn duration expressions such as "최근 24시간" into "24_time".
        pattern = re.escape(alias)
        if alias == "시간":
            pattern = rf"(?<!\d){pattern}"
        return re.search(pattern, text, flags=re.IGNORECASE)
