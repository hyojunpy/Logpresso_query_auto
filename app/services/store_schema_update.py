from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.build_store_schema_knowledge import build


class StoreSchemaUpdateError(ValueError):
    pass


class StoreSchemaUpdate:
    REQUIRED_SHEETS = {"제품_목록", "스키마_목록", "필드_상세", "Raw_양식_공개", "공통_Syslog_필드"}

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def parse_xlsx(self, content: bytes, filename: str) -> dict:
        if not filename.lower().endswith(".xlsx"):
            raise StoreSchemaUpdateError(".xlsx 파일만 사용할 수 있습니다.")
        if len(content) > 25 * 1024 * 1024:
            raise StoreSchemaUpdateError("카탈로그 파일은 25MB 이하여야 합니다.")
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
                handle.write(content)
                temporary = Path(handle.name)
            payload = build(temporary)
            payload["source"] = Path(filename).name
        except Exception as error:
            raise StoreSchemaUpdateError(f"Store 카탈로그를 읽을 수 없습니다: {error}") from error
        finally:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)
        stats = payload.get("stats", {})
        if not stats.get("products") or not stats.get("schemas"):
            raise StoreSchemaUpdateError("제품 또는 실제 스키마가 없는 카탈로그입니다.")
        return payload

    def current(self, bundled: dict) -> dict:
        if not self.path.exists():
            return bundled
        return json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def compare(current: dict, candidate: dict) -> dict:
        def product_names(payload: dict) -> set[str]:
            return {str(item.get("name")) for item in payload.get("products", [])}

        def schema_names(payload: dict) -> set[tuple[str, str]]:
            return {
                (str(product.get("name")), str(schema.get("name")))
                for product in payload.get("products", []) for schema in product.get("schemas", [])
            }

        old_products, new_products = product_names(current), product_names(candidate)
        old_schemas, new_schemas = schema_names(current), schema_names(candidate)
        old_stats, new_stats = current.get("stats", {}), candidate.get("stats", {})
        return {
            "current_version": current.get("version"), "candidate_version": candidate.get("version"),
            "stats_before": old_stats, "stats_after": new_stats,
            "products_added": sorted(new_products - old_products),
            "products_removed": sorted(old_products - new_products),
            "schemas_added": [f"{p} / {s}" for p, s in sorted(new_schemas - old_schemas)],
            "schemas_removed": [f"{p} / {s}" for p, s in sorted(old_schemas - new_schemas)],
        }

    def save(self, payload: dict) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self.path.with_name(f"store-schema-{stamp}.json")
            backup.write_bytes(self.path.read_bytes())
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return self.path
