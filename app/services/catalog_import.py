from __future__ import annotations

import csv
from dataclasses import dataclass

from app.models.request import Catalog, CatalogField, CatalogTable


REQUIRED_CSV_COLUMNS = ("table_name", "field_name", "field_type", "description")


@dataclass(frozen=True)
class CatalogImportError(ValueError):
    message: str
    row: int | None = None

    def __str__(self) -> str:
        return f"{self.message} (row {self.row})" if self.row else self.message


def catalog_from_csv_bytes(content: bytes) -> Catalog:
    """Parse a customer-supplied catalog before it reaches the persistent store."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CatalogImportError("CSV must be encoded as UTF-8") from error

    reader = csv.DictReader(text.splitlines())
    header = tuple(reader.fieldnames or ())
    missing = [column for column in REQUIRED_CSV_COLUMNS if column not in header]
    if missing:
        raise CatalogImportError("Missing required CSV columns: " + ", ".join(missing))

    tables: dict[str, CatalogTable] = {}
    seen_fields: set[tuple[str, str]] = set()
    for row_number, row in enumerate(reader, start=2):
        table_name = (row.get("table_name") or "").strip()
        field_name = (row.get("field_name") or "").strip()
        field_type = (row.get("field_type") or "unknown").strip() or "unknown"
        description = (row.get("description") or "").strip() or None
        if not table_name:
            raise CatalogImportError("table_name is required", row_number)
        if not field_name:
            raise CatalogImportError("field_name is required", row_number)
        key = (table_name, field_name)
        if key in seen_fields:
            raise CatalogImportError(f"Duplicate field: {table_name}.{field_name}", row_number)
        seen_fields.add(key)
        nullable = _nullable_value(row.get("nullable"), row_number)
        table = tables.setdefault(
            table_name,
            CatalogTable(
                table_name=table_name,
                node=(row.get("node") or "").strip() or None,
                namespace=(row.get("namespace") or "").strip() or None,
                description=(row.get("table_description") or "").strip() or None,
            ),
        )
        table.fields.append(CatalogField(field_name=field_name, field_type=field_type, description=description, nullable=nullable))

    if not tables:
        raise CatalogImportError("CSV has no catalog rows")
    return Catalog(tables=list(tables.values()), source="manual")


def _nullable_value(value: str | None, row_number: int) -> bool | None:
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise CatalogImportError("nullable must be true or false", row_number)
