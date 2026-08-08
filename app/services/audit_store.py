from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class AuditStore:
    """Stores management metadata only; never request, query, or log content."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def record(self, action: str, resource: str, *, actor: str | None = None, metadata: dict[str, object] | None = None) -> dict[str, object]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""create table if not exists management_audit (
                id integer primary key, action text not null, resource text not null,
                actor text, metadata text not null, created_at text not null
            )""")
            cursor = conn.execute(
                "insert into management_audit(action, resource, actor, metadata, created_at) values (?, ?, ?, ?, ?)",
                (action[:120], resource[:240], actor[:120] if actor else None, json.dumps(metadata or {}, ensure_ascii=False), created_at),
            )
            conn.commit()
        return {"id": cursor.lastrowid, "created_at": created_at}

    def recent(self, limit: int = 50) -> list[dict[str, object]]:
        if not self.db_path.exists():
            return []
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute("select 1 from sqlite_master where type = 'table' and name = 'management_audit'").fetchone()
            if not exists:
                return []
            rows = conn.execute(
                "select action, resource, actor, metadata, created_at from management_audit order by id desc limit ?", (max(1, min(limit, 200)),)
            ).fetchall()
        return [
            {"action": action, "resource": resource, "actor": actor, "metadata": json.loads(metadata), "created_at": created_at}
            for action, resource, actor, metadata, created_at in rows
        ]
