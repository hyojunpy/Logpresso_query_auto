from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class MetricsStore:
    """Stores aggregate counters only; never records request, query, or IP data."""
    def __init__(self, db_path: Path): self.db_path = db_path

    def increment(self, metric: str) -> None:
        day = datetime.now(UTC).date().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("create table if not exists operational_metric (day text not null, metric text not null, count integer not null, primary key(day, metric))")
            conn.execute("insert into operational_metric(day, metric, count) values (?, ?, 1) on conflict(day, metric) do update set count=count+1", (day, metric[:80]))
            conn.commit()

    def summary(self) -> dict[str, int]:
        if not self.db_path.exists(): return {}
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute("select 1 from sqlite_master where type='table' and name='operational_metric'").fetchone()
            if not exists: return {}
            return dict(conn.execute("select metric, sum(count) from operational_metric group by metric order by metric").fetchall())
