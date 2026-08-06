from __future__ import annotations

import re

from app.models.response import QueryQualityResult, ValidationIssue, ValidationResult


class QueryQualityAnalyzer:
    def analyze(self, query: str, validation: ValidationResult) -> QueryQualityResult:
        diagnostics: list[ValidationIssue] = []
        lowered = query.lower()
        if not re.search(r"\b(?:duration|from|to|window)=", lowered):
            diagnostics.append(self._issue("missing_time_range", "기간 제한이 없어 대량 조회가 될 수 있습니다.", "최근 24시간 조건을 추가할까요?", "warning"))
        if not re.search(r"\blimit\s+\d+|\blimit=\d+", lowered):
            diagnostics.append(self._issue("missing_result_limit", "결과 제한이 없습니다.", "결과를 100건으로 제한할까요?", "warning"))
        limit_match = re.search(r"\blimit\s*=?(\d+)", lowered)
        if limit_match and int(limit_match.group(1)) > 10_000:
            diagnostics.append(self._issue("excessive_result_limit", "결과 제한이 10,000건을 초과합니다.", "필요한 결과 수로 limit을 더 낮추세요.", "warning"))
        if lowered.startswith("fulltext") and " from " not in lowered:
            diagnostics.append(self._issue("broad_fulltext", "전체 범위 fulltext 검색입니다.", "대상 테이블과 기간을 좁히세요.", "warning"))
        if lowered.startswith("fulltext") and not re.search(r"\bduration=|\bfrom=", lowered):
            diagnostics.append(self._issue("fulltext_without_time_range", "Fulltext 검색에 기간이 없습니다.", "최근 24시간 같은 기간 조건을 추가할까요?", "warning"))
        if any(command in lowered for command in ("admin", "delete", "drop", "truncate", "system")):
            diagnostics.append(self._issue("privileged_command", "관리자 권한 또는 변경 가능성이 있는 명령입니다.", "권한과 영향 범위를 확인하세요.", "error"))
        if re.search(r"\bstream\s+forward=t\b", lowered):
            diagnostics.append(self._issue("data_forwarding_command", "조회 결과를 스트림으로 전달하는 명령입니다.", "대상 스트림과 전달 범위를 확인하세요.", "warning"))
        if re.search(r"\b(?:stats|rollup|timechart)\b", lowered) and "| sort" not in lowered:
            diagnostics.append(self._issue("aggregation_not_sorted", "집계 결과 정렬이 없어 우선순위 확인이 어렵습니다.", "집계 값을 기준으로 정렬하세요.", "info"))
        if self._has_unfiltered_aggregation(lowered):
            diagnostics.append(self._issue("aggregation_without_pre_filter", "집계 전에 범위를 줄이는 필터가 없습니다.", "기간 또는 검색 조건으로 집계 대상을 줄이세요.", "warning"))
        diagnostics.extend(self._timechart_diagnostics(lowered))
        if re.search(r"\b(?:stream)?join\b", lowered) and not re.search(r"\b(?:duration|from|to)=|\blimit\s+\d+", lowered):
            diagnostics.append(self._issue("unbounded_join", "기간과 결과 제한이 없는 조인입니다.", "조인 전 양쪽 데이터의 기간과 결과 수를 제한하세요.", "warning"))
        if re.search(r"\b(?:stream)?join\b", lowered):
            before_join = lowered.split("join", 1)[0]
            if "search " not in before_join:
                diagnostics.append(self._issue("join_without_pre_filter", "조인 전에 대상을 줄이는 필터가 없습니다.", "왼쪽 또는 오른쪽 조인 소스에 기간·검색 조건을 추가하세요.", "warning"))
        diagnostics.extend(self._contradictions(query))
        diagnostics.extend(validation.errors + validation.warnings)
        errors = sum(1 for item in diagnostics if item.severity == "error")
        warnings = sum(1 for item in diagnostics if item.severity == "warning")
        risk = "critical" if errors else "high" if any(item.code == "data_forwarding_command" for item in diagnostics) or warnings >= 3 else "medium" if warnings else "low"
        score_reasons = {
            "safety_score": [item.code for item in diagnostics if item.severity == "error" or item.code in {"data_forwarding_command", "privileged_command"}],
            "performance_score": [item.code for item in diagnostics if item.code in {"missing_time_range", "missing_result_limit", "broad_fulltext", "fulltext_without_time_range", "unbounded_join", "join_without_pre_filter", "excessive_result_limit"}],
            "completeness_score": [item.code for item in diagnostics if item.code in {"missing_time_range", "missing_result_limit", "fulltext_without_time_range"} or item.severity == "error"],
            "confidence_score": [item.code for item in diagnostics if item.severity in {"warning", "error"}],
        }
        return QueryQualityResult(
            safety_score=max(0, 100 - errors * 45 - warnings * 12),
            performance_score=max(0, 100 - sum(25 for item in diagnostics if item.code in {"missing_time_range", "broad_fulltext"}) - sum(12 for item in diagnostics if item.code == "missing_result_limit")),
            completeness_score=max(0, 100 - sum(20 for item in diagnostics if item.code in {"missing_time_range", "missing_result_limit"}) - errors * 20),
            confidence_score=max(0, 100 - errors * 35 - warnings * 8),
            risk_level=risk, diagnostics=diagnostics, score_reasons=score_reasons,
        )

    @staticmethod
    def _has_unfiltered_aggregation(query: str) -> bool:
        segments = [segment.strip() for segment in query.split("|") if segment.strip()]
        aggregation_index = next((index for index, segment in enumerate(segments) if re.match(r"(?:stats|rollup|timechart)\b", segment)), None)
        if aggregation_index is None:
            return False
        prior = " ".join(segments[:aggregation_index])
        return "search " not in prior and not re.search(r"\b(?:duration|from|to)=", prior)

    def _timechart_diagnostics(self, query: str) -> list[ValidationIssue]:
        if not re.search(r"\btimechart\b", query):
            return []
        span = re.search(r"\bspan=(\d+)([smhdw])\b", query)
        if not span:
            return [self._issue("timechart_span_unspecified", "시간 차트 버킷 크기를 확인하지 못했습니다.", "조회 기간에 맞는 span을 명시하세요.", "warning")]
        duration = re.search(r"\bduration=(\d+)([smhdw])\b", query)
        if not duration:
            return []
        unit_seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        total_seconds = int(duration.group(1)) * unit_seconds[duration.group(2)]
        span_seconds = int(span.group(1)) * unit_seconds[span.group(2)]
        if total_seconds / span_seconds > 10_000:
            return [self._issue("timechart_excessive_buckets", "조회 기간 대비 시간 차트 버킷 수가 과도할 수 있습니다.", "span을 더 크게 하거나 기간을 줄이세요.", "warning")]
        return []

    def _contradictions(self, query: str) -> list[ValidationIssue]:
        values: dict[str, set[str]] = {}
        for field, value in re.findall(r"\b([A-Za-z_][\w]*)\s*==\s*(\"[^\"]*\"|'[^']*'|\S+)", query):
            values.setdefault(field, set()).add(value)
        issues = [self._issue("contradictory_filter", f"'{field}'에 서로 다른 동등 조건이 함께 있습니다.", "조건을 하나로 정리하세요.", "warning", field) for field, items in values.items() if len(items) > 1]
        bounds: dict[str, dict[str, float]] = {}
        for field, operator, raw_value in re.findall(r"\b([A-Za-z_][\w]*)\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)", query):
            value = float(raw_value)
            field_bounds = bounds.setdefault(field, {})
            if operator in {">", ">="}:
                field_bounds["lower"] = max(field_bounds.get("lower", value), value)
            else:
                field_bounds["upper"] = min(field_bounds.get("upper", value), value)
        for field, bound in bounds.items():
            if "lower" in bound and "upper" in bound and bound["lower"] > bound["upper"]:
                issues.append(self._issue("contradictory_range", f"'{field}'의 최소값이 최대값보다 큽니다.", "숫자 범위 조건을 다시 확인하세요.", "warning", field))
        return issues

    @staticmethod
    def _issue(code: str, message: str, suggestion: str, severity: str, field: str | None = None) -> ValidationIssue:
        return ValidationIssue(code=code, message=message, severity=severity, affected_field=field, suggestion=suggestion, source="policy")
