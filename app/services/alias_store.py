from __future__ import annotations

import sqlite3
import csv
import io
from pathlib import Path


class AliasImportError(ValueError):
    pass


class AliasStore:
    """Local business vocabulary. Admin APIs using this store need authentication in shared deployments."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def list(self, scope: str | None = None) -> list[dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            rows = conn.execute("select phrase, target, kind, scope from query_alias where scope='' or scope=? order by phrase", (scope or "",)).fetchall()
        return [{"phrase": phrase, "target": target, "kind": kind, "scope": scope} for phrase, target, kind, scope in rows]

    def save(self, phrase: str, target: str, kind: str = "table", scope: str = "") -> dict[str, str]:
        item = self._normalized(phrase, target, kind, scope)
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            conn.execute("delete from query_alias where phrase=? and kind=? and scope=?", (item["phrase"], item["kind"], item["scope"]))
            conn.execute("insert into query_alias(phrase, target, kind, scope) values (?, ?, ?, ?)", tuple(item.values()))
        return item

    def import_csv_bytes(self, content: bytes) -> int:
        try:
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        except UnicodeDecodeError as error:
            raise AliasImportError("CSV must use UTF-8 encoding") from error
        if not rows or not rows[0]:
            raise AliasImportError("CSV must contain at least one alias row")
        required = {"phrase", "target"}
        headers = set(rows[0])
        if not required.issubset(headers):
            raise AliasImportError("CSV headers must include phrase,target")
        if len(rows) > 1000:
            raise AliasImportError("CSV can contain at most 1000 aliases")
        items: list[dict[str, str]] = []
        keys: set[tuple[str, str, str]] = set()
        for number, row in enumerate(rows, start=2):
            try:
                item = self._normalized(row.get("phrase", ""), row.get("target", ""), row.get("kind") or "table", row.get("scope") or "")
            except ValueError as error:
                raise AliasImportError(f"row {number}: {error}") from error
            key = (item["phrase"], item["kind"], item["scope"])
            if key in keys:
                raise AliasImportError(f"row {number}: duplicate phrase, kind, and scope")
            keys.add(key)
            items.append(item)
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            for item in items:
                conn.execute("delete from query_alias where phrase=? and kind=? and scope=?", (item["phrase"], item["kind"], item["scope"]))
                conn.execute("insert into query_alias(phrase, target, kind, scope) values (?, ?, ?, ?)", tuple(item.values()))
            conn.commit()
        return len(items)

    def delete(self, phrase: str, kind: str, scope: str = "") -> bool:
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            deleted = conn.execute("delete from query_alias where phrase=? and kind=? and scope=?", (phrase, kind, scope)).rowcount
        return bool(deleted)

    def diagnostics(self) -> list[dict[str, object]]:
        """Report ambiguous vocabulary without changing alias resolution behavior."""
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            rows = conn.execute(
                "select phrase, kind, group_concat(distinct target), count(distinct target) "
                "from query_alias group by phrase, kind having count(distinct target) > 1"
            ).fetchall()
        return [
            {"code": "alias_conflict", "phrase": phrase, "kind": kind, "targets": targets.split(","), "count": count}
            for phrase, kind, targets, count in rows
        ]

    def export_csv(self, scope: str | None = None) -> str:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=["phrase", "target", "kind", "scope"])
        writer.writeheader()
        writer.writerows(self.list(scope))
        return "\ufeff" + output.getvalue()

    @staticmethod
    def _normalized(phrase: str, target: str, kind: str, scope: str) -> dict[str, str]:
        item = {"phrase": phrase.strip(), "target": target.strip(), "kind": kind.strip(), "scope": scope.strip()}
        if item["kind"] not in {"table", "field"}:
            raise ValueError("kind must be table or field")
        if not item["phrase"] or not item["target"]:
            raise ValueError("phrase and target are required")
        if len(item["phrase"]) > 120 or len(item["target"]) > 120 or len(item["scope"]) > 120:
            raise ValueError("phrase, target, and scope must be at most 120 characters")
        return item

    @staticmethod
    def _ensure(conn: sqlite3.Connection) -> None:
        conn.execute("create table if not exists query_alias (phrase text not null, target text not null, kind text not null, scope text not null default '')")
        columns = {row[1] for row in conn.execute("pragma table_info(query_alias)")}
        if "scope" not in columns:
            conn.execute("alter table query_alias add column scope text not null default ''")
