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
    if metric.startswith("ollama_"):
        return f"Ollama {metric.removeprefix('ollama_').replace('_', ' ')}"
    return metric


def duration_bucket_metric(name: str, milliseconds: int) -> str:
    for threshold in (250, 1_000, 5_000, 15_000, 45_000):
        if milliseconds < threshold:
            return f"{name}_lt_{threshold}ms"
    return f"{name}_gte_45000ms"


def operational_overview(metrics: dict[str, int]) -> dict[str, int | list[str]]:
    """Summarize aggregate operational counters without exposing any request content."""
    generation_total = sum(
        count for metric, count in metrics.items() if metric.startswith("generation_") and metric != "generation_llm_fallback"
    )
    fallback_count = metrics.get("generation_llm_fallback", 0)
    ollama_requests = sum(count for metric, count in metrics.items() if metric.startswith("ollama_client_duration_ms_"))
    slow_ollama_count = metrics.get("ollama_client_duration_ms_gte_45000ms", 0)
    warnings: list[str] = []
    if slow_ollama_count:
        warnings.append("Ollama 응답이 timeout 구간에 도달한 요청이 있습니다.")
    if fallback_count:
        warnings.append("규칙 기반 fallback이 발생한 요청이 있습니다.")
    return {
        "generation_total": generation_total,
        "fallback_count": fallback_count,
        "ollama_requests": ollama_requests,
        "slow_ollama_count": slow_ollama_count,
        "warnings": warnings,
    }


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

    def daily_summary(self, days: int = 7) -> list[dict[str, str | int]]:
        if not self.db_path.exists():
            return []
        window = max(1, min(days, self.retention_days))
        cutoff = (datetime.now(UTC).date() - timedelta(days=window - 1)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute(
                "select 1 from sqlite_master where type='table' and name='operational_metric'"
            ).fetchone()
            if not exists:
                return []
            return [
                {"day": day, "metric": metric, "count": count}
                for day, metric, count in conn.execute(
                    "select day, metric, count from operational_metric "
                    "where day >= ? order by day desc, metric",
                    (cutoff,),
                ).fetchall()
            ]
