from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import re
import shlex
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.models.request import Catalog, CatalogField, CatalogTable, GenerateQueryRequest


@dataclass(frozen=True)
class StoreSchemaMatch:
    product: str | None
    schema_name: str | None
    log_types: tuple[str, ...]
    discriminator_field: str | None
    schema_aliases: tuple[str, ...]
    fields: tuple[dict[str, Any], ...]
    replacements: tuple[tuple[str, str], ...]
    raw_format: dict[str, Any] | None = None

    @property
    def log_type(self) -> str | None:
        return self.log_types[0] if len(self.log_types) == 1 else None


class StoreSchemaKnowledge:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> "StoreSchemaKnowledge":
        resource = files("app.resources").joinpath("logpresso_store_schema.json")
        return cls(json.loads(resource.read_text(encoding="utf-8")))

    @classmethod
    def active(cls, override_path: str | Path | None = None) -> "StoreSchemaKnowledge":
        path = Path(override_path) if override_path else None
        if path and path.exists():
            return cls(json.loads(path.read_text(encoding="utf-8")))
        return cls.bundled()

    def match(
        self, text: str, product_hint: str | None = None, schema_hint: str | None = None
    ) -> StoreSchemaMatch | None:
        products = self.payload.get("products", [])
        product = next((item for item in products if item.get("name") == product_hint), None)
        product = product or self._matching_product(text, products)
        schemas = product.get("schemas", []) if product else [
            schema for item in products for schema in item.get("schemas", [])
        ]
        hinted_schema = next((item for item in schemas if item.get("name") == schema_hint), None)
        matched = [hinted_schema] if hinted_schema else self._matching_schemas(
            text,
            schemas,
            include_short_aliases=product is not None,
            include_log_types=product is not None,
        )
        raw_format = self._matching_raw_format(text, product) if product else None
        if not matched and not product:
            return None
        active_schemas = matched or schemas
        log_types = tuple(dict.fromkeys(
            str(code) for schema in matched for code in schema.get("log_types", []) if code
        ))
        discriminator_fields = {
            schema.get("discriminator_field") for schema in matched if schema.get("discriminator_field")
        }
        discriminator_field = next(iter(discriminator_fields)) if len(discriminator_fields) == 1 else None
        if not matched and raw_format and raw_format.get("log_type"):
            log_types = (str(raw_format["log_type"]),)
        fields = self._unique_fields(active_schemas)
        schema_aliases: tuple[str, ...] = ()
        if len(matched) == 1:
            schema_aliases = tuple([*matched[0].get("aliases", []), *matched[0].get("short_aliases", [])])
        return StoreSchemaMatch(
            product=product.get("name") if product else None,
            schema_name=matched[0].get("name") if len(matched) == 1 else None,
            log_types=log_types,
            discriminator_field=discriminator_field,
            schema_aliases=schema_aliases,
            fields=tuple(fields),
            replacements=tuple(self._field_replacements(text, fields)),
            raw_format=raw_format,
        )

    def enrich(self, payload: GenerateQueryRequest) -> GenerateQueryRequest:
        match = self.match(payload.request, payload.context.store_product, payload.context.store_schema)
        if match is None:
            return payload
        context = payload.context.model_copy(deep=True)
        request = payload.request
        if match.schema_name:
            for alias in sorted(match.schema_aliases, key=len, reverse=True):
                is_semantic_collision = any(word in alias.lower() for word in ("차단", "거부", "deny", "block"))
                if is_semantic_collision and self._contains(request, alias):
                    replacement = (
                        match.schema_name
                        if not any(word in match.schema_name.lower() for word in ("차단", "거부", "deny", "block"))
                        else "Store 보안 이벤트"
                    )
                    request = re.sub(re.escape(alias), replacement, request, count=1, flags=re.IGNORECASE)
                    break
        for phrase, field_name in match.replacements:
            request = self._replace_field_alias(request, phrase, field_name)
        known_fields = [field["name"] for field in match.fields]
        if match.discriminator_field:
            known_fields.append(match.discriminator_field)
        context.known_fields = list(dict.fromkeys([*context.known_fields, *known_fields]))
        if match.product and not context.product:
            context.product = match.product
        if len(context.known_tables) == 1 and match.fields and context.request_catalog is None:
            catalog_fields = [CatalogField(
                field_name=field["name"], field_type=field["type"],
                description=field.get("display_name") or field.get("description") or None,
            ) for field in match.fields]
            if match.discriminator_field and match.discriminator_field not in {field.field_name for field in catalog_fields}:
                catalog_fields.append(CatalogField(
                    field_name=match.discriminator_field,
                    field_type="string",
                    description="로그 유형 구분 필드",
                ))
            context.request_catalog = Catalog(
                source="external_sync",
                catalog_version=str(self.payload.get("version") or "unknown"),
                tables=[CatalogTable(
                    table_name=context.known_tables[0],
                    description=f"{match.product or 'Logpresso Store'} {match.schema_name or 'schema'}",
                    fields=catalog_fields,
                )],
            )
        return payload.model_copy(update={"request": request, "context": context})

    def status(self) -> dict[str, Any]:
        stats = dict(self.payload.get("stats", {}))
        products = self.payload.get("products", [])
        stats.update({
            "version": self.payload.get("version"),
            "source": self.payload.get("source"),
            "manufacturers": len({item.get("manufacturer") for item in products if item.get("manufacturer")}),
            "products_with_raw_formats": sum(bool(item.get("raw_formats")) for item in products),
            "schemas_without_fields": sum(
                not schema.get("fields") for item in products for schema in item.get("schemas", [])
            ),
        })
        return stats

    def coverage(self, *, missing_only: bool = False, limit: int = 500) -> list[dict[str, Any]]:
        rows = []
        for product in self.payload.get("products", []):
            for schema in product.get("schemas", []):
                field_count = len(schema.get("fields", []))
                if missing_only and field_count:
                    continue
                rows.append({
                    "manufacturer": product.get("manufacturer"),
                    "product": product.get("name"),
                    "schema": schema.get("name"),
                    "field_count": field_count,
                    "log_type_count": len(schema.get("log_types", [])),
                    "has_raw_format": bool(product.get("raw_formats")),
                    "status": schema.get("status"),
                })
        rows.sort(key=lambda item: (item["field_count"] > 0, not item["has_raw_format"], str(item["product"]), str(item["schema"])))
        return rows[:max(1, min(limit, 2_000))]

    def detect_raw(self, raw_line: str, product_hint: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        candidates = []
        for product in self.payload.get("products", []):
            if product_hint and product.get("name") != product_hint:
                continue
            for format_ in product.get("raw_formats", []):
                result = self.validate_raw(str(product.get("name")), str(format_.get("log_type")), raw_line)
                expected = int(result.get("expected_fields") or 0)
                actual = int(result.get("actual_fields") or 0)
                closeness = 1.0 if result.get("valid") else max(0.0, 1 - abs(expected - actual) / max(expected, 1))
                marker = str(format_.get("log_type") or "").split("/", 1)[0].strip().lower()
                marker_match = bool(marker and marker in raw_line[:80].lower())
                score = min(1.0, closeness * 0.75 + (0.25 if marker_match else 0))
                candidates.append({
                    "product": product.get("name"), "log_type": format_.get("log_type"),
                    "score": round(score, 3), "valid": bool(result.get("valid")),
                    "expected_fields": expected, "actual_fields": actual,
                    "delimiter": result.get("delimiter"), "reason": result.get("reason"),
                })
        return sorted(candidates, key=lambda item: (-item["score"], str(item["product"])))[:max(1, min(limit, 20))]

    def preflight(self, product_name: str, schema_name: str | None, mapped_table: str | None) -> dict[str, Any]:
        product = next((item for item in self.payload.get("products", []) if item.get("name") == product_name), None)
        schema = next((item for item in (product or {}).get("schemas", []) if item.get("name") == schema_name), None)
        issues = []
        if not product:
            issues.append("unknown_product")
        if schema_name and not schema:
            issues.append("unknown_schema")
        if schema and not schema.get("fields"):
            issues.append("fields_unavailable")
        if not mapped_table:
            issues.append("table_mapping_missing")
        return {
            "ready": not issues,
            "issues": issues,
            "product": product_name,
            "schema": schema_name,
            "table": mapped_table,
            "field_count": len((schema or {}).get("fields", [])),
            "raw_format_count": len((product or {}).get("raw_formats", [])),
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        needle = self._normalize(query)
        results = []
        for product in self.payload.get("products", []):
            for schema in product.get("schemas", []):
                phrases = [
                    product.get("manufacturer", ""), product.get("name", ""), schema.get("name", ""),
                    *product.get("aliases", []), *schema.get("short_aliases", []), *schema.get("log_types", []),
                ]
                haystacks = [self._normalize(str(value)) for value in phrases if value]
                contains = any(needle and needle in value for value in haystacks)
                similarity = max((SequenceMatcher(None, needle, value).ratio() for value in haystacks), default=0)
                if contains or similarity >= 0.55:
                    results.append({
                        "manufacturer": product.get("manufacturer"), "product": product.get("name"),
                        "schema": schema.get("name"), "log_types": schema.get("log_types", []),
                        "field_count": len(schema.get("fields", [])), "score": round(1.0 if contains else similarity, 3),
                    })
        return sorted(results, key=lambda item: (-item["score"], -item["field_count"], str(item["schema"])))[:max(1, min(limit, 100))]

    def validate_raw(self, product_name: str, log_type: str, raw_line: str) -> dict[str, Any]:
        product = next((item for item in self.payload.get("products", []) if item.get("name") == product_name), None)
        if not product:
            return {"valid": False, "reason": "unknown_product"}
        format_ = next((item for item in product.get("raw_formats", []) if str(item.get("log_type", "")).lower() == log_type.lower()), None)
        if not format_:
            return {"valid": False, "reason": "raw_format_unavailable"}
        template = str(format_.get("template") or "")
        delimiter = "pipe"
        expected = [part.strip() for part in template.split("|") if part.strip()]
        actual = raw_line.rstrip("\r\n").split("|")
        if len(expected) <= 1 and "`%{" in template:
            delimiter = "backtick"
            expected = re.findall(r"%\{([^}]+)\}", template)
            actual = [part for part in raw_line.rstrip("\r\n").split("`") if part]
            if actual and ":" in actual[0]:
                actual[0] = actual[0].split(":", 1)[1]
        elif len(expected) <= 1 and "%" in template:
            delimiter = "whitespace"
            expected = re.findall(r"%[A-Za-z0-9_]+", template)
            try:
                actual = shlex.split(raw_line.rstrip("\r\n"))
            except ValueError:
                actual = []
        if len(expected) <= 1:
            return {
                "valid": False,
                "reason": "unsupported_template",
                "transport": format_.get("transport"),
                "source_url": format_.get("source_url"),
            }
        return {
            "valid": len(actual) == len(expected),
            "reason": "matched" if len(actual) == len(expected) else "field_count_mismatch",
            "expected_fields": len(expected), "actual_fields": len(actual),
            "field_names": expected, "transport": format_.get("transport"),
            "delimiter": delimiter,
            "source_url": format_.get("source_url"),
        }

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z가-힣]+", "", value.lower())

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        if phrase.isascii() and re.fullmatch(r"[A-Za-z0-9_-]+", phrase):
            return bool(re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(phrase)}(?![A-Za-z0-9_-])", text, flags=re.IGNORECASE
            ))
        return phrase.lower() in text.lower()

    def _matching_product(self, text: str, products: list[dict[str, Any]]) -> dict[str, Any] | None:
        scored = []
        for product in products:
            lengths = [len(alias) for alias in product.get("aliases", []) if self._contains(text, alias)]
            if lengths:
                scored.append((max(lengths), product))
        if not scored:
            return None
        best = max(score for score, _ in scored)
        winners = [product for score, product in scored if score == best]
        return winners[0] if len(winners) == 1 else None

    def _matching_schemas(
        self, text: str, schemas: list[dict[str, Any]], *,
        include_short_aliases: bool, include_log_types: bool,
    ) -> list[dict[str, Any]]:
        scored = []
        for schema in schemas:
            phrases = list(schema.get("aliases", []))
            if include_short_aliases:
                phrases.extend(schema.get("short_aliases", []))
            if include_log_types:
                phrases.extend(schema.get("log_types", []))
            lengths = [len(phrase) for phrase in phrases if len(phrase) >= 2 and self._contains(text, phrase)]
            if lengths:
                scored.append((max(lengths), schema))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        return [schema for score, schema in scored if score == best]

    def _matching_raw_format(self, text: str, product: dict[str, Any]) -> dict[str, Any] | None:
        matches = [item for item in product.get("raw_formats", []) if item.get("log_type") and self._contains(text, str(item["log_type"]))]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _unique_fields(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields_by_name: dict[str, dict[str, Any]] = {}
        for schema in schemas:
            for field in schema.get("fields", []):
                fields_by_name.setdefault(field["name"], field)
        return list(fields_by_name.values())

    def _field_replacements(self, text: str, fields: list[dict[str, Any]]) -> list[tuple[str, str]]:
        aliases: dict[str, set[str]] = {}
        for field in fields:
            for alias in field.get("aliases", []):
                if self._field_alias_match(text, alias):
                    aliases.setdefault(alias, set()).add(field["name"])
        replacements = [(alias, next(iter(names))) for alias, names in aliases.items() if len(names) == 1]
        replacements.sort(key=lambda item: len(item[0]), reverse=True)
        accepted: list[tuple[str, str]] = []
        occupied: list[tuple[int, int]] = []
        for alias, target in replacements:
            found = self._field_alias_match(text, alias)
            if not found or any(found.start() < end and start < found.end() for start, end in occupied):
                continue
            occupied.append(found.span())
            accepted.append((alias, target))
        return accepted

    @staticmethod
    def _field_alias_match(text: str, alias: str) -> re.Match[str] | None:
        return re.search(StoreSchemaKnowledge._field_alias_pattern(alias), text, flags=re.IGNORECASE)

    @staticmethod
    def _field_alias_pattern(alias: str) -> str:
        pattern = re.escape(alias)
        return rf"(?<!\d){pattern}" if alias == "시간" else pattern

    @staticmethod
    def _replace_field_alias(text: str, alias: str, target: str) -> str:
        return re.sub(StoreSchemaKnowledge._field_alias_pattern(alias), target, text, flags=re.IGNORECASE)
