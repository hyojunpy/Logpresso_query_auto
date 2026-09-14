from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import re
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

    def match(self, text: str) -> StoreSchemaMatch | None:
        products = self.payload.get("products", [])
        product = self._matching_product(text, products)
        schemas = product.get("schemas", []) if product else [
            schema for item in products for schema in item.get("schemas", [])
        ]
        matched = self._matching_schemas(
            text, schemas,
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
        match = self.match(payload.request)
        if match is None:
            return payload
        context = payload.context.model_copy(deep=True)
        request = payload.request
        if match.schema_name and not self._contains(request, match.schema_name):
            for alias in sorted(match.schema_aliases, key=len, reverse=True):
                is_semantic_collision = any(word in alias.lower() for word in ("차단", "거부", "deny", "block"))
                if alias != match.schema_name and is_semantic_collision and self._contains(request, alias):
                    request = re.sub(re.escape(alias), match.schema_name, request, count=1, flags=re.IGNORECASE)
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
