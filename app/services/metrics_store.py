from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


def metric_label(metric: str) -> str:
    labels = {
        "generation_generated": "쿼리 생성 완료",
        "generation_needs_clarification": "추가 정보 요청",
        "generation_unsupported": "지원하지 않는 요청",
        "generation_llm_fallback": "LLM fallback 사용",
    }
    if metric in labels:
        return labels[metric]
    if metric.startswith("http_status_"):
        return f"HTTP {metric.removeprefix('http_status_')} 응답"
    return metric


class MetricsStore:
    """Stores aggregate counters only; never records request, query, or IP data."""
    def __init__(self, db_path: Path, retention_days: int = 30):
        self.db_path = db_path
        self.retention_days = max(1, retention_days)

    def increment(self, metric: str, occurred_at: datetime | None = None) -> None:
        timestamp = occurred_at or datetime.now(UTC)
        day = timestamp.date().isoformat()
        cutoff = (timestamp.date() - timedelta(days=self.retention_days)).isoformat()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "create table if not exists operational_metric (day text not null, metric text not null, count integer not null, primary key(day, metric))"
            )
            conn.execute("delete from operational_metric where day < ?", (cutoff,))
            conn.execute(
                "insert into operational_metric(day, metric, count) values (?, ?, 1) "
                "on conflict(day, metric) do update set count=count+1",
                (day, metric[:80]),
            )

    def summary(self) -> dict[str, int]:
        if not self.db_path.exists(): return {}
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute(
                "select 1 from sqlite_master where type='table' and name='operational_metric'"
            ).fetchone()
            if not exists: return {}
            return dict(
                conn.execute(
                    "select metric, sum(count) from operational_metric group by metric order by metric"
                ).fetchall()
            )
