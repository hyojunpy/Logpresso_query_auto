from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


TABLE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


class StoreTableMapping:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = Lock()

    def list(self) -> list[dict[str, str | None]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [item for item in payload.get("mappings", []) if self._valid_item(item)]

    def resolve(self, product: str | None, schema: str | None) -> str | None:
        if not product:
            return None
        mappings = self.list()
        exact = next((item for item in mappings if item["product"] == product and item.get("schema") == schema), None)
        fallback = next((item for item in mappings if item["product"] == product and not item.get("schema")), None)
        selected = exact or fallback
        return str(selected["table"]) if selected else None

    def save(self, product: str, table: str, schema: str | None = None) -> list[dict[str, str | None]]:
        product, table = product.strip(), table.strip()
        schema = schema.strip() if schema else None
        if not product:
            raise ValueError("제품을 선택하세요.")
        if not TABLE_RE.fullmatch(table):
            raise ValueError("테이블 이름 형식이 올바르지 않습니다.")
        with self._lock:
            items = [
                item for item in self.list()
                if not (item["product"] == product and item.get("schema") == schema)
            ]
            items.append({"product": product, "schema": schema, "table": table})
            items.sort(key=lambda item: (str(item["product"]), str(item.get("schema") or "")))
            self._write(items)
        return items

    def delete(self, product: str, schema: str | None = None) -> list[dict[str, str | None]]:
        with self._lock:
            items = [
                item for item in self.list()
                if not (item["product"] == product and item.get("schema") == schema)
            ]
            self._write(items)
        return items

    def _write(self, items: list[dict[str, str | None]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mappings": items,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _valid_item(item: object) -> bool:
        return (
            isinstance(item, dict)
            and isinstance(item.get("product"), str)
            and isinstance(item.get("table"), str)
            and bool(TABLE_RE.fullmatch(item["table"]))
            and (item.get("schema") is None or isinstance(item.get("schema"), str))
        )
