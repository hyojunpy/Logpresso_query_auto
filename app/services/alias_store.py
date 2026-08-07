from __future__ import annotations

import sqlite3
from pathlib import Path


class AliasStore:
    """Local business vocabulary. Admin APIs using this store need authentication in shared deployments."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def list(self) -> list[dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            rows = conn.execute("select phrase, target, kind from query_alias order by phrase").fetchall()
        return [{"phrase": phrase, "target": target, "kind": kind} for phrase, target, kind in rows]

    def save(self, phrase: str, target: str, kind: str = "table") -> dict[str, str]:
        if kind not in {"table", "field"}:
            raise ValueError("kind must be table or field")
        if not phrase.strip() or not target.strip():
            raise ValueError("phrase and target are required")
        with sqlite3.connect(self.db_path) as conn:
            self._ensure(conn)
            conn.execute(
                "insert into query_alias(phrase, target, kind) values (?, ?, ?) "
                "on conflict(phrase, kind) do update set target=excluded.target",
                (phrase.strip(), target.strip(), kind),
            )
        return {"phrase": phrase.strip(), "target": target.strip(), "kind": kind}

    @staticmethod
    def _ensure(conn: sqlite3.Connection) -> None:
        conn.execute("create table if not exists query_alias (phrase text not null, target text not null, kind text not null, unique(phrase, kind))")
