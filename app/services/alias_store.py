from __future__ import annotations

import sqlite3
import csv
import io
from pathlib import Path


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
        if kind not in {"table", "field"}:
            raise ValueError("kind must be table or field")
        if not phrase.strip() or not target.strip():
            raise ValueError("phrase and target are required")
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            conn.execute("delete from query_alias where phrase=? and kind=? and scope=?", (phrase.strip(), kind, scope.strip()))
            conn.execute("insert into query_alias(phrase, target, kind, scope) values (?, ?, ?, ?)", (phrase.strip(), target.strip(), kind, scope.strip()))
        return {"phrase": phrase.strip(), "target": target.strip(), "kind": kind, "scope": scope.strip()}

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
    def _ensure(conn: sqlite3.Connection) -> None:
        conn.execute("create table if not exists query_alias (phrase text not null, target text not null, kind text not null, scope text not null default '')")
        columns = {row[1] for row in conn.execute("pragma table_info(query_alias)")}
        if "scope" not in columns:
            conn.execute("alter table query_alias add column scope text not null default ''")
