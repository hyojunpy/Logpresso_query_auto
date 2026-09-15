from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from uuid import uuid4

from app.models.dashboard import DashboardDefinition, DashboardRecord, DashboardSummary


class DashboardStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS dashboard_revisions (
                    dashboard_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, change_note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dashboard_id, revision)
                );
                CREATE TABLE IF NOT EXISTS dashboard_heads (
                    dashboard_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
                );
            """)

    def _connect(self):
        return sqlite3.connect(self.path)

    def save(self, dashboard: DashboardDefinition, dashboard_id: str | None = None, change_note: str = "") -> DashboardRecord:
        dashboard_id = dashboard_id or uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute("SELECT revision FROM dashboard_heads WHERE dashboard_id=?", (dashboard_id,)).fetchone()
            revision = (row[0] if row else 0) + 1
            connection.execute(
                "INSERT INTO dashboard_revisions VALUES (?, ?, ?, ?, ?)",
                (dashboard_id, revision, dashboard.model_dump_json(), change_note, now),
            )
            connection.execute(
                "INSERT INTO dashboard_heads VALUES (?, ?, 0, ?) ON CONFLICT(dashboard_id) DO UPDATE SET revision=excluded.revision, deleted=0, updated_at=excluded.updated_at",
                (dashboard_id, revision, now),
            )
        return self.get(dashboard_id)

    def get(self, dashboard_id: str, revision: int | None = None) -> DashboardRecord:
        with self._connect() as connection:
            if revision is None:
                head = connection.execute("SELECT revision, deleted FROM dashboard_heads WHERE dashboard_id=?", (dashboard_id,)).fetchone()
                if not head or head[1]:
                    raise KeyError(dashboard_id)
                revision = head[0]
            row = connection.execute(
                "SELECT payload, created_at FROM dashboard_revisions WHERE dashboard_id=? AND revision=?",
                (dashboard_id, revision),
            ).fetchone()
            head_time = connection.execute("SELECT updated_at FROM dashboard_heads WHERE dashboard_id=?", (dashboard_id,)).fetchone()
        if not row:
            raise KeyError(f"{dashboard_id}:{revision}")
        return DashboardRecord(id=dashboard_id, revision=revision, dashboard=DashboardDefinition.model_validate_json(row[0]), created_at=row[1], updated_at=(head_time or (row[1],))[0])

    def list(self) -> list[DashboardSummary]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT h.dashboard_id, h.revision, r.payload, h.updated_at
                FROM dashboard_heads h JOIN dashboard_revisions r
                ON r.dashboard_id=h.dashboard_id AND r.revision=h.revision
                WHERE h.deleted=0 ORDER BY h.updated_at DESC
            """).fetchall()
        return [DashboardSummary(id=item[0], revision=item[1], title=(d := DashboardDefinition.model_validate_json(item[2])).title, scope=d.scope, panel_count=len(d.panels), updated_at=item[3]) for item in rows]

    def revisions(self, dashboard_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT revision, change_note, created_at FROM dashboard_revisions WHERE dashboard_id=? ORDER BY revision DESC", (dashboard_id,)).fetchall()
        return [{"revision": row[0], "change_note": row[1], "created_at": row[2]} for row in rows]

    def clone(self, dashboard_id: str, title: str | None = None) -> DashboardRecord:
        dashboard = self.get(dashboard_id).dashboard.model_copy(deep=True)
        dashboard.title = title or f"{dashboard.title} 복사본"
        return self.save(dashboard, change_note=f"cloned from {dashboard_id}")

    def delete(self, dashboard_id: str) -> None:
        with self._connect() as connection:
            result = connection.execute("UPDATE dashboard_heads SET deleted=1, updated_at=? WHERE dashboard_id=? AND deleted=0", (datetime.now(timezone.utc).isoformat(), dashboard_id))
        if not result.rowcount:
            raise KeyError(dashboard_id)

    def restore(self, dashboard_id: str, revision: int, change_note: str) -> DashboardRecord:
        return self.save(self.get(dashboard_id, revision).dashboard, dashboard_id, change_note)

    def diff(self, dashboard_id: str, old_revision: int, new_revision: int) -> str:
        old = json.dumps(self.get(dashboard_id, old_revision).dashboard.model_dump(), ensure_ascii=False, indent=2, sort_keys=True)
        new = json.dumps(self.get(dashboard_id, new_revision).dashboard.model_dump(), ensure_ascii=False, indent=2, sort_keys=True)
        return "\n".join(unified_diff(old.splitlines(), new.splitlines(), fromfile=f"revision-{old_revision}", tofile=f"revision-{new_revision}", lineterm=""))
