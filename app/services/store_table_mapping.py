from __future__ import annotations

import json
import re
import csv
from io import StringIO
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

    def export_csv(self) -> str:
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=["product", "schema", "table"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.list())
        return output.getvalue()

    def import_csv(self, content: bytes) -> list[dict[str, str | None]]:
        try:
            text = content.decode("utf-8-sig")
            rows = list(csv.DictReader(StringIO(text)))
        except (UnicodeDecodeError, csv.Error) as error:
            raise ValueError("매핑 CSV를 읽을 수 없습니다.") from error
        if not rows or set(rows[0]) != {"product", "schema", "table"}:
            raise ValueError("CSV 헤더는 product,schema,table 이어야 합니다.")
        validated = []
        for number, row in enumerate(rows, start=2):
            product = (row.get("product") or "").strip()
            schema = (row.get("schema") or "").strip() or None
            table = (row.get("table") or "").strip()
            if not product or not TABLE_RE.fullmatch(table):
                raise ValueError(f"CSV {number}행의 제품 또는 테이블 이름이 올바르지 않습니다.")
            validated.append({"product": product, "schema": schema, "table": table})
        with self._lock:
            merged = {(item["product"], item.get("schema")): item for item in self.list()}
            merged.update({(item["product"], item.get("schema")): item for item in validated})
            items = sorted(merged.values(), key=lambda item: (str(item["product"]), str(item.get("schema") or "")))
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
