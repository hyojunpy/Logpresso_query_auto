from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.models.request import FeedbackRequest


class FeedbackStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def save(self, feedback: FeedbackRequest) -> dict[str, object]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""create table if not exists query_feedback (
                id integer primary key, request_text text, generated_query text, request_hash text not null,
                result_status text not null, rating text not null, feedback_comment text, issue_type text, created_at text not null
            )""")
            request_text = self._safe_text(feedback.request_text) if feedback.store_raw_text else None
            query = self._safe_text(feedback.generated_query) if feedback.store_raw_text else None
            comment = self._safe_text(feedback.feedback_comment)
            created_at = datetime.now(UTC).isoformat()
            cursor = conn.execute("insert into query_feedback(request_text, generated_query, request_hash, result_status, rating, feedback_comment, issue_type, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)", (request_text, query, self._hash(feedback.request_text), feedback.result_status, feedback.rating, comment, feedback.issue_type, created_at))
            conn.commit()
        return {"id": cursor.lastrowid, "created_at": created_at, "raw_text_stored": feedback.store_raw_text}

    def summary(self) -> dict[str, object]:
        if not self.db_path.exists():
            return {"total": 0, "ratings": {}, "issue_types": {}}
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute("select 1 from sqlite_master where type = 'table' and name = 'query_feedback'").fetchone()
            if not exists:
                return {"total": 0, "ratings": {}, "issue_types": {}}
            ratings = dict(conn.execute("select rating, count(*) from query_feedback group by rating").fetchall())
            issues = dict(conn.execute("select issue_type, count(*) from query_feedback where issue_type is not null group by issue_type").fetchall())
            total = conn.execute("select count(*) from query_feedback").fetchone()[0]
        return {"total": total, "ratings": ratings, "issue_types": issues}

    def improvement_candidates(self) -> list[dict[str, str | int]]:
        summary = self.summary()
        suggestions = {
            "wrong_table": ("테이블 별칭 또는 카탈로그 보강", "업무 표현과 실제 테이블 이름의 매핑을 등록하세요."),
            "wrong_field": ("필드 별칭 또는 카탈로그 보강", "업무 용어와 실제 필드 이름의 매핑을 등록하세요."),
            "wrong_time_range": ("기간 해석 규칙 검토", "기본 기간 또는 기간 표현 별칭을 검토하세요."),
            "invalid_syntax": ("문법 템플릿 검토", "생성된 명령과 옵션을 문서 근거로 재검토하세요."),
            "irrelevant_query": ("요청 의도/별칭 보강", "업무 표현에 대한 별칭 또는 평가셋을 추가하세요."),
        }
        return [
            {"issue_type": issue, "count": count, "title": suggestions[issue][0], "suggestion": suggestions[issue][1]}
            for issue, count in summary["issue_types"].items()
            if issue in suggestions
        ]

    def improvement_report(self) -> dict[str, object]:
        """Aggregate only masked feedback metadata for an operational improvement view."""
        summary = self.summary()
        candidates = self.improvement_candidates()
        return {
            "total_feedback": summary["total"],
            "ratings": summary["ratings"],
            "issue_types": summary["issue_types"],
            "candidates": candidates,
            "priority_issue_types": [item["issue_type"] for item in candidates],
        }

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_text(value: str | None) -> str | None:
        if not value:
            return None
        masked = re.sub(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*\S+", r"\1=[REDACTED]", value)
        masked = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", masked)
        masked = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", masked)
        masked = re.sub(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b", "[IP]", masked)
        return masked[:1000]
