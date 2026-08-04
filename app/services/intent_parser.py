from __future__ import annotations

from datetime import date, timedelta
import re

from app.models.request import (
    Aggregation,
    FilterCondition,
    GenerateQueryRequest,
    QueryIntent,
    RenameOperation,
    SortCondition,
    TimeRange,
)


ERROR_WORDS = ("에러", "오류", "ERROR", "error", "실패", "fail", "failed")
DENY_WORDS = ("차단", "deny", "blocked", "block")
COUNT_WORDS = ("건수", "카운트", "count", "집계", "통계", "횟수")
COUNT_ONLY_WORDS = ("건수", "카운트", "count", "횟수")
AGGREGATION_WORDS = {
    "평균": "avg",
    "avg": "avg",
    "average": "avg",
    "합계": "sum",
    "총합": "sum",
    "sum": "sum",
    "최대": "max",
    "최댓값": "max",
    "max": "max",
    "최소": "min",
    "최솟값": "min",
    "min": "min",
}
SAMPLE_FIELD_CANDIDATES = ("line", "message", "event", "raw", "_raw")


class IntentParser:
    def parse(self, payload: GenerateQueryRequest) -> QueryIntent:
        text = payload.request.strip()
        context = payload.context
        intent = QueryIntent(objective=text)
        intent.time_range = self._time_range(text)
        intent.query_type = "adhoc"
        intent.source_type = self._source_type(text)
        intent.tables = self._tables(
            text,
            context.known_tables,
            allow_single_default=intent.source_type == "table",
        ) if intent.source_type in {"table", "fulltext"} else []
        intent.fulltext_expression = self._fulltext_expression(text) if intent.source_type == "fulltext" else None
        intent.use_parameterized_time_range = self._looks_like_parameterized_time_range(text)
        intent.streams = self._streams(text) if intent.source_type == "stream" else []
        intent.stream_window = self._realtime_window(text) if intent.source_type == "stream" else None
        intent.loggers = self._loggers(text) if intent.source_type == "logger" else []
        intent.logger_window = self._realtime_window(text) if intent.source_type == "logger" else None
        if intent.source_type == "file":
            intent.file_path = self._file_path(text)
            intent.file_command = self._file_command(intent.file_path)
            intent.archive_member = self._archive_member(text) if intent.file_command == "zipfile" else None
        intent.selected_fields = self._selected_fields(text, context.known_fields)
        intent.computed_fields = self._computed_fields(text, context.known_fields)
        intent.parser_name = self._parser_name(text)
        intent.structured_parser = self._structured_parser(text)
        intent.structured_parser_field = self._structured_parser_field(text) if intent.structured_parser else None
        intent.parser_flatten = intent.structured_parser == "parsejson" and any(
            word in text.lower() for word in ("flatten", "중첩을 펼", "중첩까지 펼", "배열을 펼")
        )
        intent.parser_tab = intent.structured_parser == "parsecsv" and any(
            word in text.lower() for word in ("tsv", "tab=t", "탭 구분")
        )
        intent.explode_fields = self._explode_fields(text, context.known_fields)
        intent.renames = self._renames(text, context.known_fields)
        intent.aggregations = self._aggregations(text, context.known_fields)
        intent.group_by = self._group_by(text, context.known_fields)
        intent.aggregation_command = "rollup" if self._looks_like_ratio(text) and intent.group_by else "stats"
        intent.final_aggregations = self._final_aggregations(text, intent.group_by)
        intent.post_filters = self._post_filters(text, intent.aggregations)
        intent.filters = self._filters(text, context.known_fields, intent.post_filters)
        intent.sort = self._sort(text, intent.aggregations, context.known_fields)
        intent.limit = self._limit(text)

        if "실시간" in text:
            intent.query_type = "realtime"
        if "예약" in text or "스케줄" in text:
            intent.query_type = "scheduled"
        if intent.source_type == "stream":
            intent.query_type = "stream"
        if intent.source_type == "logger":
            intent.query_type = "realtime"

        self._collect_missing_information(intent, text, context.known_fields)
        return intent

    def _source_type(self, text: str) -> str:
        if "스트림" in text:
            return "stream"
        if self._looks_like_fulltext(text):
            return "fulltext"
        if any(word in text.lower() for word in ("logger", "로거", "로그 수집기")):
            return "logger"
        if self._file_path(text) or "파일" in text:
            return "file"
        return "table"

    def _time_range(self, text: str) -> TimeRange | None:
        compact_units = {"분": "m", "시간": "h", "시": "h", "일": "d", "주": "w"}
        explicit_datetime = self._explicit_datetime_range(text)
        if explicit_datetime:
            return explicit_datetime
        relative_datetime = self._relative_datetime_range(text)
        if relative_datetime:
            return relative_datetime
        explicit = self._explicit_date_range(text)
        if explicit:
            return explicit
        relative_absolute = self._relative_absolute_range(text)
        if relative_absolute:
            return relative_absolute
        match = re.search(r"(?:최근|지난)\s*(\d+)\s*(분|시간|시|일|주)", text)
        if match:
            return TimeRange(mode="duration", duration=f"{match.group(1)}{compact_units[match.group(2)]}")
        relative = {
            "최근 하루": "1d",
            "지난 하루": "1d",
            "오늘": "1d",
            "최근 일주일": "7d",
            "지난 일주일": "7d",
            "지난 7일": "7d",
            "최근 7일": "7d",
        }
        for phrase, duration in relative.items():
            if phrase in text:
                return TimeRange(mode="duration", duration=duration)
        return None

    def _explicit_datetime_range(self, text: str) -> TimeRange | None:
        date_pattern = r"\d{4}-\d{1,2}-\d{1,2}"
        time_pattern = self._time_token_pattern()
        match = re.search(
            rf"({date_pattern})\s+({time_pattern})\s*(?:부터|에서|~|-)\s*({date_pattern})?\s*({time_pattern})\s*(?:까지)?",
            text,
        )
        if not match:
            return None
        start_date = self._normalize_date(match.group(1))
        start = f"{start_date} {self._normalize_time(match.group(2))}"
        end_date = self._normalize_date(match.group(3)) if match.group(3) else start_date
        end = f"{end_date} {self._normalize_time(match.group(4))}"
        return self._absolute_range(start, end)

    def _relative_datetime_range(self, text: str) -> TimeRange | None:
        day = r"오늘|어제"
        time_pattern = self._time_token_pattern()
        match = re.search(rf"({day})\s*({time_pattern})\s*(?:부터|에서|~|-)\s*({day})?\s*({time_pattern})\s*(?:까지)?", text)
        if not match:
            return None
        start_date = self._relative_day(match.group(1))
        end_date = self._relative_day(match.group(3)) if match.group(3) else start_date
        start = f"{start_date} {self._normalize_time(match.group(2))}"
        end = f"{end_date} {self._normalize_time(match.group(4))}"
        return self._absolute_range(start, end)

    def _explicit_date_range(self, text: str) -> TimeRange | None:
        date_pattern = r"\d{4}-\d{1,2}-\d{1,2}"
        match = re.search(rf"({date_pattern})\s*(?:부터|에서|~|-)\s*({date_pattern})\s*(?:까지)?", text)
        if not match:
            return None
        start = self._normalize_date(match.group(1))
        end = self._normalize_date(match.group(2))
        if "까지" in match.group(0):
            end = self._add_days(end, 1)
        return self._absolute_range(start, end)

    def _relative_absolute_range(self, text: str) -> TimeRange | None:
        today = date.today()
        if "어제" in text:
            start = today - timedelta(days=1)
            return self._absolute_range(start.isoformat(), today.isoformat())
        if "오늘" in text:
            return self._absolute_range(today.isoformat(), (today + timedelta(days=1)).isoformat())
        if "지난주" in text or "지난 주" in text:
            this_monday = today - timedelta(days=today.weekday())
            previous_monday = this_monday - timedelta(days=7)
            return self._absolute_range(previous_monday.isoformat(), this_monday.isoformat())
        if "이번주" in text or "이번 주" in text:
            this_monday = today - timedelta(days=today.weekday())
            return self._absolute_range(this_monday.isoformat(), (this_monday + timedelta(days=7)).isoformat())
        if "지난달" in text or "지난 달" in text:
            first_this_month = today.replace(day=1)
            last_month_last_day = first_this_month - timedelta(days=1)
            first_last_month = last_month_last_day.replace(day=1)
            return self._absolute_range(first_last_month.isoformat(), first_this_month.isoformat())
        if "이번달" in text or "이번 달" in text:
            first_this_month = today.replace(day=1)
            first_next_month = self._first_day_next_month(today)
            return self._absolute_range(first_this_month.isoformat(), first_next_month.isoformat())
        return None

    def _absolute_range(self, start: str, end: str) -> TimeRange:
        return TimeRange.model_validate({"mode": "absolute", "from": start, "to": end})

    def _normalize_date(self, value: str) -> str:
        year, month, day = (int(part) for part in value.split("-"))
        return date(year, month, day).isoformat()

    def _normalize_time(self, value: str) -> str:
        stripped = re.sub(r"\s+", "", value.strip())
        if stripped == "정오":
            return "12:00:00"
        if stripped == "자정":
            return "00:00:00"
        modifier = ""
        for prefix in ("오전", "오후", "밤", "새벽"):
            if stripped.startswith(prefix):
                modifier = prefix
                stripped = stripped[len(prefix):]
                break
        stripped = stripped.rstrip("시")
        parts = [int(part) for part in stripped.split(":")]
        while len(parts) < 3:
            parts.append(0)
        hour, minute, second = parts[:3]
        if modifier in {"오후", "밤"} and hour < 12:
            hour += 12
        if modifier == "오전" and hour == 12:
            hour = 0
        if modifier == "새벽" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}:{second:02d}"

    def _time_token_pattern(self) -> str:
        numeric = r"(?:오전|오후|밤|새벽)?\s*\d{1,2}(?::\d{1,2})?(?::\d{1,2})?\s*시?"
        return rf"(?:정오|자정|{numeric})"

    def _relative_day(self, value: str) -> str:
        today = date.today()
        if value == "어제":
            return (today - timedelta(days=1)).isoformat()
        return today.isoformat()

    def _add_days(self, value: str, days: int) -> str:
        year, month, day = (int(part) for part in value.split("-"))
        return (date(year, month, day) + timedelta(days=days)).isoformat()

    def _first_day_next_month(self, value: date) -> date:
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    def _tables(self, text: str, known_tables: list[str], allow_single_default: bool = True) -> list[str]:
        tables = [table for table in known_tables if table in text]
        explicit = re.findall(
            r"([A-Za-z_*][A-Za-z0-9_*.-]*(?::[A-Za-z_][A-Za-z0-9_*.-]*)?)\s*(?:에서|의|테이블)",
            text,
        )
        for table in explicit:
            if table not in tables and table not in {"rename", "as"}:
                tables.append(table)
        if self._looks_like_parameterized_time_range(text):
            parameter_tables = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:을|를)?\s*(?:동적으로|매개변수|파라미터)", text)
            for table in parameter_tables:
                if table not in tables and table not in {"set", "setq", "table"}:
                    tables.append(table)
        if allow_single_default and not tables and len(known_tables) == 1:
            tables.append(known_tables[0])
        return tables

    def _fulltext_expression(self, text: str) -> str | None:
        ip_range = re.search(
            r"\b((?:\d{1,3}\.){3}\d{1,3})\s*(?:~|부터|에서)\s*((?:\d{1,3}\.){3}\d{1,3})\b",
            text,
        )
        if ip_range:
            return f'iprange("{ip_range.group(1)}", "{ip_range.group(2)}")'
        numeric_range = re.search(r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:~|부터|에서)\s*(-?\d+(?:\.\d+)?)(?![\d.])", text)
        if numeric_range and any(word in text for word in ("범위", "사이", "range")):
            return f"range({numeric_range.group(1)}, {numeric_range.group(2)})"
        boolean_expression = self._fulltext_boolean_expression(text)
        if boolean_expression:
            return boolean_expression
        ip = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        if ip:
            return ip.group(0)
        quoted = re.search(r"['\"]([^'\"]+)['\"]", text)
        if quoted:
            return quoted.group(1).strip()
        patterns = [
            r"([A-Za-z0-9_.:/-]+)\s*(?:가|이)?\s*(?:포함된|포함한|포함되어|포함)",
            r"([A-Za-z0-9_.:/-]+)\s*(?:문자열|텍스트)?\s*(?:검색|찾아)",
        ]
        ignored = {"로그", "테이블", "전체", "모든", "검색", "fulltext"}
        for pattern in patterns:
            for candidate in re.findall(pattern, text, flags=re.IGNORECASE):
                if candidate not in ignored:
                    return candidate
        return None

    def _fulltext_boolean_expression(self, text: str) -> str | None:
        quoted_terms = [term.strip() for term in re.findall(r"['\"]([^'\"]+)['\"]", text) if term.strip()]
        lowered = text.lower()
        has_or = any(word in lowered for word in (" 또는 ", " 혹은 ", " or "))
        has_and = any(word in lowered for word in (" 그리고 ", " 및 ", " and ", "포함하면서", "포함하고"))
        if len(quoted_terms) >= 3 and has_and and has_or:
            return (
                f"{self._quote_fulltext_term(quoted_terms[0])} and "
                f"({self._quote_fulltext_term(quoted_terms[1])} or {self._quote_fulltext_term(quoted_terms[2])})"
            )
        if len(quoted_terms) >= 2 and (has_and or has_or):
            operator = "or" if has_or and not has_and else "and"
            return f" {operator} ".join(self._quote_fulltext_term(term) for term in quoted_terms)

        token = r"[가-힣A-Za-z0-9_.:/-]+"
        combined = re.search(
            rf"({token})\s*(?:을|를)?\s*포함(?:하면서|하고).*?({token})\s*(?:또는|혹은|or)\s*({token})",
            text,
            flags=re.IGNORECASE,
        )
        if combined:
            first, second, third = combined.groups()
            return (
                f"{self._quote_fulltext_term(first)} and "
                f"({self._quote_fulltext_term(second)} or {self._quote_fulltext_term(third)})"
            )
        alternative = re.search(
            rf"({token})\s*(?:또는|혹은|or)\s*({token}).*?(?:포함|검색|찾아)",
            text,
            flags=re.IGNORECASE,
        )
        if alternative:
            return " or ".join(self._quote_fulltext_term(term) for term in alternative.groups())
        conjunction = re.search(
            rf"({token})\s*(?:와|과|그리고|및|and)\s*({token}).*?(?:모두\s*)?(?:포함|검색|찾아)",
            text,
            flags=re.IGNORECASE,
        )
        if conjunction:
            return " and ".join(self._quote_fulltext_term(term) for term in conjunction.groups())
        return None

    def _quote_fulltext_term(self, term: str) -> str:
        escaped = term.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _streams(self, text: str) -> list[str]:
        match = re.search(
            r"([A-Za-z_][A-Za-z0-9_*.-]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_*.-]*)*)\s*스트림",
            text,
        )
        return [item.strip() for item in match.group(1).split(",")] if match else []

    def _parser_name(self, text: str) -> str | None:
        explicit = re.search(r"\bparse\s+([A-Za-z_][A-Za-z0-9_.-]*)\b", text, flags=re.IGNORECASE)
        if explicit:
            return explicit.group(1)
        patterns = [
            r"\b([A-Za-z_][A-Za-z0-9_.-]*)\s*파서(?:로|를\s*사용(?:해서|하여)?|를\s*적용)",
            r"\b([A-Za-z_][A-Za-z0-9_.-]*)\s*parser(?:로|를\s*사용(?:해서|하여)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _structured_parser(self, text: str) -> str | None:
        lowered = text.lower()
        if not self._looks_like_parse(text):
            return None
        if "parsejson" in lowered or "json" in lowered:
            return "parsejson"
        if "parsecsv" in lowered or "csv" in lowered or "tsv" in lowered:
            return "parsecsv"
        return None

    def _structured_parser_field(self, text: str) -> str | None:
        explicit = re.search(r"\bfield\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\b", text, flags=re.IGNORECASE)
        if explicit:
            return explicit.group(1)
        match = re.search(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*필드(?:에\s*저장된|의)?\s*(?:JSON|CSV|TSV)",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    def _explode_fields(self, text: str, known_fields: list[str]) -> list[str]:
        explicit = re.findall(r"\bexplode\s+([A-Za-z_][A-Za-z0-9_]*)\b", text, flags=re.IGNORECASE)
        fields = [field for field in explicit if not known_fields or field in known_fields]
        if any(word in text.lower() for word in ("explode", "배열", "행으로", "원소별")):
            for field in known_fields:
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", text) and field not in fields:
                    fields.append(field)
        return fields

    def _loggers(self, text: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*\\[A-Za-z_][A-Za-z0-9_*.-]*)\b", text)))

    def _realtime_window(self, text: str) -> str | None:
        units = {"초": "s", "분": "m", "시간": "h", "일": "d", "주": "w"}
        match = re.search(r"(\d+)\s*(초|분|시간|일|주)\s*(?:간|동안)?", text)
        if match:
            return f"{match.group(1)}{units[match.group(2)]}"
        match = re.search(r"\bwindow\s*=\s*(\d+(?:y|mon|w|d|h|m|s))\b", text, flags=re.IGNORECASE)
        return match.group(1).lower() if match else None

    def _file_path(self, text: str) -> str | None:
        extensions = r"evtx|eml|lnk|csv|tsv|json|txt|pcap|xml|pf|wer|zip"
        quoted = re.search(rf"['\"]([^'\"]+\.(?:{extensions}))['\"]", text, flags=re.IGNORECASE)
        if quoted:
            return quoted.group(1)
        match = re.search(
            rf"(?<![A-Za-z0-9_.-])((?:[A-Za-z]:\\|/)?[^\s'\"]+\.(?:{extensions}))\b",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    def _file_command(self, path: str | None) -> str | None:
        if not path:
            return None
        extension_commands = {
            ".evtx": "evtx-file",
            ".eml": "eml-file",
            ".lnk": "lnk-file",
            ".csv": "csvfile",
            ".tsv": "csvfile",
            ".json": "jsonfile",
            ".txt": "textfile",
            ".pcap": "pcapfile",
            ".xml": "xmlfile",
            ".pf": "prefetch-file",
            ".wer": "wer-file",
            ".zip": "zipfile",
        }
        lowered = path.lower()
        return next((command for extension, command in extension_commands.items() if lowered.endswith(extension)), None)

    def _archive_member(self, text: str) -> str | None:
        match = re.search(
            r"\.zip['\"]?\s*(?:파일\s*)?(?:안의|내의|에서)\s*['\"]?([^\s'\"]+)['\"]?",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    def _filters(
        self,
        text: str,
        known_fields: list[str],
        post_filters: list[FilterCondition] | None = None,
    ) -> list[FilterCondition]:
        filters: list[FilterCondition] = []
        has_explicit_string_filter = self._looks_like_string_filter(text)
        if "root" in text:
            field = self._field_or_missing(known_fields, "login_name", "user")
            if field:
                filters.append(FilterCondition(field=field, value="root"))
        if not has_explicit_string_filter and any(word in text for word in DENY_WORDS):
            field = self._labeled_filter_field(text, ("차단", "deny", "blocked"), known_fields)
            field = field or self._field_or_missing(known_fields, "action")
            if field:
                filters.append(FilterCondition(field=field, value="deny"))
        if not has_explicit_string_filter and any(word in text for word in ERROR_WORDS):
            field = self._labeled_filter_field(text, ERROR_WORDS, known_fields)
            field = field or self._field_or_missing(known_fields, "level", "severity", "message", "line")
            if field:
                value = "ERROR" if field in {"message", "line"} else "error"
                filters.append(FilterCondition(field=field, value=value))
        ip = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        if ip:
            field = self._field_or_missing(known_fields, "src_ip", "ip")
            if field:
                filters.append(FilterCondition(field=field, value=ip.group(0), value_type="ip"))
        filters.extend(self._comparison_filters(text, known_fields))
        filters.extend(self._string_comparison_filters(text, known_fields))
        filters.extend(self._contains_filters(text, known_fields))
        return self._without_post_filters(self._unique_filters(filters), post_filters or [])

    def _labeled_filter_field(
        self,
        text: str,
        labels: tuple[str, ...],
        known_fields: list[str],
    ) -> str | None:
        label_pattern = "|".join(re.escape(label) for label in labels)
        match = re.search(
            rf"(?:{label_pattern})\s*필드(?:는|은|로|:)?\s*([A-Za-z_][A-Za-z0-9_]*)",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        field = match.group(1)
        return field if not known_fields or field in known_fields else None

    def _comparison_filters(self, text: str, known_fields: list[str]) -> list[FilterCondition]:
        operator_map = {
            "이상": ">=",
            "초과": ">",
            "이하": "<=",
            "미만": "<",
            ">=": ">=",
            "<=": "<=",
            ">": ">",
            "<": "<",
            "==": "==",
            "=": "==",
        }
        expression = r"[A-Za-z_][A-Za-z0-9_]*(?:\s*[+\-*/]\s*[A-Za-z_][A-Za-z0-9_]*)*"
        number = r"-?\d+(?:\.\d+)?"
        filters: list[FilterCondition] = []
        korean_pattern = rf"({expression})\s*(?:가|이|은|는)?\s*({number})\s*(이상|초과|이하|미만)"
        for left, value, op in re.findall(korean_pattern, text):
            self._append_numeric_filter(filters, left, op, value, known_fields, operator_map)
        symbolic_pattern = rf"({expression})\s*(>=|<=|>|<|==|=)\s*({number})"
        for left, op, value in re.findall(symbolic_pattern, text):
            self._append_numeric_filter(filters, left, op, value, known_fields, operator_map)
        return filters

    def _append_numeric_filter(
        self,
        filters: list[FilterCondition],
        left: str,
        op: str,
        value: str,
        known_fields: list[str],
        operator_map: dict[str, str],
    ) -> None:
        normalized = re.sub(r"\s+", " ", left.strip())
        if not self._expression_fields_known(normalized, known_fields):
            return
        filters.append(
            FilterCondition(
                field=normalized,
                operator=operator_map[op],
                value=value,
                value_type="number",
            )
        )

    def _without_post_filters(
        self,
        filters: list[FilterCondition],
        post_filters: list[FilterCondition],
    ) -> list[FilterCondition]:
        post_values = {(filter_.operator, str(filter_.value), filter_.value_type) for filter_ in post_filters}
        return [
            filter_
            for filter_ in filters
            if (filter_.operator, str(filter_.value), filter_.value_type) not in post_values
        ]

    def _string_comparison_filters(self, text: str, known_fields: list[str]) -> list[FilterCondition]:
        if not known_fields:
            return []
        field = r"[A-Za-z_][A-Za-z0-9_]*"
        value = r"[가-힣A-Za-z0-9_.:/-]+"
        symbolic_value = r"[가-힣A-Za-z0-9_.:/-]+?"
        symbolic_boundary = r"(?=\s|(?:인|아닌)(?:\s|$)|[,.)]|$)"
        filters: list[FilterCondition] = []
        negative_patterns = [
            rf"({field})\s*(?:가|이|은|는)?\s*({value}?)\s*(?:이\s*)?아닌",
            rf"({field})\s*!=\s*({symbolic_value}){symbolic_boundary}",
        ]
        positive_patterns = [
            rf"({field})\s*(?:가|이|은|는)\s*({value}?)\s*인(?!\s*아닌)",
            rf"({field})\s*(?:가|이|은|는)\s*({value}?)\s*(?:이거나|거나)",
            rf"({field})\s*(?:가|이|은|는)\s*({value}?)\s*(?:같은|와\s*같은|과\s*같은)",
            rf"({field})\s*(?:==|=)\s*({symbolic_value}){symbolic_boundary}",
        ]
        for left, first, second in re.findall(
            rf"({field})\s*(?:가|이|은|는)\s*({value}?)\s*(?:또는|혹은|or)\s*({value}?)\s*인",
            text,
            flags=re.IGNORECASE,
        ):
            self._append_string_filter(filters, left, "==", first, known_fields)
            self._append_string_filter(filters, left, "==", second, known_fields, conjunction="or")
        for pattern in negative_patterns:
            for left, raw_value in re.findall(pattern, text):
                self._append_string_filter(filters, left, "!=", raw_value, known_fields)
        for pattern in positive_patterns:
            for left, raw_value in re.findall(pattern, text):
                if any(
                    item.field == left and str(item.value) == raw_value and item.operator == "!="
                    for item in filters
                ):
                    continue
                self._append_string_filter(filters, left, "==", raw_value, known_fields)
        has_or = any(word in text for word in ("또는", "혹은", "이거나", "거나", " or "))
        has_and = any(word in text for word in ("그리고", "이면서", "동시에", " 및 ", " and "))
        if has_or and not has_and:
            for filter_ in filters[1:]:
                filter_.conjunction = "or"
        elif has_or:
            for group in self._parenthesized_or_groups(text):
                indexes = [
                    index
                    for index, filter_ in enumerate(filters)
                    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(filter_.field)}(?![A-Za-z0-9_])", group)
                ]
                for index in indexes[1:]:
                    filters[index].conjunction = "or"
        return filters

    def _parenthesized_or_groups(self, text: str) -> list[str]:
        groups = re.findall(r"\(([^()]*)\)", text)
        return [
            group
            for group in groups
            if any(word in group.lower() for word in ("또는", "혹은", "이거나", "거나", " or "))
        ]

    def _contains_filters(self, text: str, known_fields: list[str]) -> list[FilterCondition]:
        if not known_fields:
            return []
        field = r"[A-Za-z_][A-Za-z0-9_]*"
        value = r"[가-힣A-Za-z0-9_.:/-]+"
        filters: list[FilterCondition] = []
        patterns = [
            rf"({field})\s*(?:에|에서|이|가|은|는)?\s*({value})\s*(?:문자열을\s*)?(?:포함|contains)",
            rf"({field})\s*(?:에|에서)\s*({value})\s*(?:가|이)?\s*포함",
        ]
        for pattern in patterns:
            for left, raw_value in re.findall(pattern, text, flags=re.IGNORECASE):
                if left not in known_fields:
                    continue
                filters.append(
                    FilterCondition(
                        field=left,
                        operator="==",
                        value=f"*{raw_value}*",
                        value_type="string",
                    )
                )
        return filters

    def _append_string_filter(
        self,
        filters: list[FilterCondition],
        field: str,
        operator: str,
        value: str,
        known_fields: list[str],
        conjunction: str = "and",
    ) -> None:
        if field not in known_fields:
            return
        filters.append(
            FilterCondition(
                field=field,
                operator=operator,
                value=value,
                value_type=self._filter_value_type(value),
                conjunction=conjunction,
            )
        )

    def _filter_value_type(self, value: str) -> str:
        return "number" if re.fullmatch(r"-?\d+(?:\.\d+)?", value) else "string"

    def _unique_filters(self, filters: list[FilterCondition]) -> list[FilterCondition]:
        unique: list[FilterCondition] = []
        seen: set[tuple[str, str, str, str]] = set()
        for filter_ in filters:
            key = (filter_.field, filter_.operator, str(filter_.value), filter_.value_type)
            if key in seen:
                continue
            seen.add(key)
            unique.append(filter_)
        return unique

    def _renames(self, text: str, known_fields: list[str]) -> list[RenameOperation]:
        if not any(word in text.lower() for word in ("rename", "이름 변경", "이름변경", "필드명 변경")):
            return []
        patterns = [
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:를|을)\s*([가-힣A-Za-z_][가-힣A-Za-z0-9_]*)\s*(?:로|으로)\s*rename",
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:를|을)\s*([가-힣A-Za-z_][가-힣A-Za-z0-9_]*)\s*(?:로|으로)\s*(?:이름\s*변경|필드명\s*변경)",
            r"rename\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:as\s+)?([가-힣A-Za-z_][가-힣A-Za-z0-9_]*)",
        ]
        renames: list[RenameOperation] = []
        for pattern in patterns:
            for field, new_name in re.findall(pattern, text, flags=re.IGNORECASE):
                if known_fields and field not in known_fields:
                    continue
                renames.append(RenameOperation(field=field, new_name=new_name))
        return renames

    def _selected_fields(self, text: str, known_fields: list[str]) -> list[str]:
        if not self._looks_like_field_selection(text):
            return []
        selected = [
            field
            for field in known_fields
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", text)
        ]
        if selected:
            return selected
        before_cue = re.split(r"(?:만\s*)?(?:보여|출력|표시|조회)", text, maxsplit=1)[0]
        candidates = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", before_cue)
        ignored = set(self._tables(text, known_fields)) | {"rename", "as", "table"}
        return [candidate for candidate in candidates if candidate not in ignored]

    def _looks_like_field_selection(self, text: str) -> bool:
        if any(phrase in text for phrase in ("데이터만", "로그만", "레코드만")):
            return False
        if self._looks_like_unique_values(text):
            return False
        if self._looks_like_sample_aggregation(text):
            return False
        if any(word in text for word in COUNT_WORDS) or self._looks_like_metric_aggregation(text):
            return False
        cues = ("만 보여", "만 출력", "만 표시", "필드만", "필드만 보여", "필드 출력", "컬럼만", "컬럼 출력")
        return any(cue in text for cue in cues)

    def _computed_fields(self, text: str, known_fields: list[str]) -> list:
        if not self._looks_like_computation(text):
            return []
        patterns = [
            r"([A-Za-z_][A-Za-z0-9_]*(?:\s*[+\-*/]\s*[A-Za-z_][A-Za-z0-9_]*)+)\s*(?:를|을)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:로|으로)\s*(?:계산|eval|생성|만들)",
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:와|과|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:의\s*)?(?:합계|합|더한\s*값)\s*(?:를|을)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:로|으로)?\s*(?:계산|생성|만들)?",
        ]
        computed = []
        for field_expr, target in re.findall(patterns[0], text, flags=re.IGNORECASE):
            expression = re.sub(r"\s+", " ", field_expr.strip())
            if self._expression_fields_known(expression, known_fields):
                from app.models.request import ComputedField

                computed.append(ComputedField(name=target, expression=expression))
        for left, right, target in re.findall(patterns[1], text, flags=re.IGNORECASE):
            expression = f"{left} + {right}"
            if self._expression_fields_known(expression, known_fields):
                from app.models.request import ComputedField

                computed.append(ComputedField(name=target, expression=expression))
        return computed

    def _looks_like_computation(self, text: str) -> bool:
        cues = ("계산", "합계", "더한 값", "eval", "계산필드", "계산 필드")
        return any(cue in text for cue in cues)

    def _expression_fields_known(self, expression: str, known_fields: list[str]) -> bool:
        if not known_fields:
            return False
        identifiers = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expression)
        return all(identifier in known_fields for identifier in identifiers)

    def _field_or_missing(self, known_fields: list[str], *preferred: str) -> str | None:
        if not known_fields:
            return None
        for name in preferred:
            if name in known_fields:
                return name
        for name in preferred:
            suffix = name.split("_")[-1]
            for field in known_fields:
                if suffix in field:
                    return field
        return None

    def _aggregations(self, text: str, known_fields: list[str]) -> list[Aggregation]:
        aggregations: list[Aggregation] = []
        if known_fields:
            field_pattern = "|".join(re.escape(field) for field in sorted(known_fields, key=len, reverse=True))
            word_pattern = "|".join(re.escape(word) for word in sorted(AGGREGATION_WORDS, key=len, reverse=True))
            patterns = [
                rf"\b({field_pattern})\b\s*(?:의\s*)?({word_pattern})",
                rf"({word_pattern})\s*(?:값|을|를|은|는|이|가)?\s*\b({field_pattern})\b",
            ]
            for field, word in re.findall(patterns[0], text, flags=re.IGNORECASE):
                self._append_aggregation(aggregations, word, field)
            for word, field in re.findall(patterns[1], text, flags=re.IGNORECASE):
                self._append_aggregation(aggregations, word, field)
            for function, field in re.findall(rf"\b(avg|sum|max|min)\s*\(\s*({field_pattern})\s*\)", text, flags=re.IGNORECASE):
                self._append_aggregation(aggregations, function, field)
        if self._looks_like_sample_aggregation(text):
            field = self._sample_field(known_fields)
            if field:
                function = self._sample_function(text)
                aggregations.append(
                    Aggregation(function=function, field=field, alias=f"{function}_{self._alias_field(field)}")
                )
        if (
            any(word in text for word in COUNT_ONLY_WORDS)
            or any(phrase in text for phrase in ("많이 나온", "적게 나온", "가장 많이", "가장 적게"))
            or self._looks_like_ratio(text)
            or self._looks_like_unique_values(text)
        ):
            aggregations.append(Aggregation(function="count"))
        return self._unique_aggregations(aggregations)

    def _final_aggregations(self, text: str, group_by: list[str]) -> list[Aggregation]:
        if not group_by or not self._looks_like_unique_count(text):
            return []
        field = group_by[0]
        return [Aggregation(function="count", alias=f"unique_{field}")]

    def _append_aggregation(self, aggregations: list[Aggregation], word: str, field: str) -> None:
        function = AGGREGATION_WORDS[word.lower() if word.isascii() else word]
        aggregations.append(Aggregation(function=function, field=field, alias=f"{function}_{field}"))

    def _unique_aggregations(self, aggregations: list[Aggregation]) -> list[Aggregation]:
        unique: list[Aggregation] = []
        seen: set[tuple[str, str | None]] = set()
        for aggregation in aggregations:
            key = (aggregation.function, aggregation.field)
            if key in seen:
                continue
            seen.add(key)
            unique.append(aggregation)
        return unique

    def _post_filters(self, text: str, aggregations: list[Aggregation]) -> list[FilterCondition]:
        filters: list[FilterCondition] = []
        if not aggregations:
            return filters
        operator_map = {
            "이상": ">=",
            "초과": ">",
            "이하": "<=",
            "미만": "<",
            ">=": ">=",
            "<=": "<=",
            ">": ">",
            "<": "<",
        }
        number = r"-?\d+(?:\.\d+)?"
        for aggregation in aggregations:
            aliases = self._aggregation_filter_names(aggregation)
            for name in aliases:
                pattern = rf"{re.escape(name)}\s*(?:이|가|은|는)?\s*({number})\s*(이상|초과|이하|미만)"
                for value, op in re.findall(pattern, text, flags=re.IGNORECASE):
                    filters.append(
                        FilterCondition(
                            field=aggregation.alias or aggregation.function,
                            operator=operator_map[op],
                            value=value,
                            value_type="number",
                        )
                    )
                symbolic = rf"{re.escape(name)}\s*(>=|<=|>|<)\s*({number})"
                for op, value in re.findall(symbolic, text, flags=re.IGNORECASE):
                    filters.append(
                        FilterCondition(
                            field=aggregation.alias or aggregation.function,
                            operator=operator_map[op],
                            value=value,
                            value_type="number",
                        )
                    )
        return self._unique_filters(filters)

    def _aggregation_filter_names(self, aggregation: Aggregation) -> list[str]:
        if aggregation.function == "count":
            return ["count", "건수", "카운트", "횟수"]
        names = [aggregation.alias or "", aggregation.function]
        if aggregation.field:
            names.append(aggregation.field)
            metric_words = {
                "avg": "평균",
                "sum": "합계",
                "max": "최대",
                "min": "최소",
            }
            if aggregation.function in metric_words:
                names.append(f"{aggregation.field} {metric_words[aggregation.function]}")
                names.append(f"{aggregation.field}의 {metric_words[aggregation.function]}")
        return [name for name in names if name]

    def _group_by(self, text: str, known_fields: list[str]) -> list[str]:
        groups = [
            field
            for field in known_fields
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])\s*(?:별|별로)", text)
        ]
        if groups:
            return groups
        if any(phrase in text for phrase in ("많이 나온", "적게 나온", "가장 많이", "가장 적게")):
            mentioned = [
                field
                for field in known_fields
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", text)
            ]
            if mentioned:
                return mentioned[:1]
        if self._looks_like_unique_values(text):
            mentioned = [
                field
                for field in known_fields
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", text)
            ]
            if mentioned:
                return mentioned[:1]
        if "IP별" in text or "출발지 IP" in text:
            field = self._field_or_missing(known_fields, "src_ip", "ip")
            return [field] if field else []
        if "사용자" in text and ("별" in text or "사용자의" in text):
            field = self._field_or_missing(known_fields, "login_name", "user")
            return [field] if field else []
        return []

    def _sort(
        self,
        text: str,
        aggregations: list[Aggregation],
        known_fields: list[str],
    ) -> list[SortCondition]:
        candidates = list(dict.fromkeys(
            known_fields
            + [aggregation.alias for aggregation in aggregations if aggregation.alias]
            + ["count"]
        ))
        if candidates:
            field_pattern = "|".join(re.escape(field) for field in sorted(candidates, key=len, reverse=True))
            explicit = re.findall(
                rf"(?<![A-Za-z0-9_])({field_pattern})(?![A-Za-z0-9_])\s*(?:을|를|기준으로)?\s*"
                r"(내림차순|오름차순|높은 순|낮은 순|많은 순|적은 순)",
                text,
                flags=re.IGNORECASE,
            )
            if explicit:
                descending = {"내림차순", "높은 순", "많은 순"}
                return [
                    SortCondition(field=field, direction="desc" if direction in descending else "asc")
                    for field, direction in explicit
                ]
        sort_field = self._sort_field(text, aggregations)
        lowered = text.lower()
        if any(word in lowered for word in ("top", "상위", "많은 순", "높은 순", "큰 순", "내림차순", "많이", "가장 많이", "많이 나온")):
            return [SortCondition(field=sort_field, direction="desc")]
        if any(word in lowered for word in ("bottom", "하위", "적은 순", "낮은 순", "작은 순", "오름차순", "가장 적게", "적게 나온")):
            return [SortCondition(field=sort_field, direction="asc")]
        return []

    def _sort_field(self, text: str, aggregations: list[Aggregation]) -> str:
        for aggregation in aggregations:
            if aggregation.field and aggregation.field in text and aggregation.alias:
                return aggregation.alias
        if len(aggregations) == 1 and aggregations[0].alias:
            return aggregations[0].alias
        return "count"

    def _limit(self, text: str) -> int | None:
        top_bottom = re.search(r"(?:top|bottom|상위|하위)\s*(\d+)", text, flags=re.IGNORECASE)
        if top_bottom:
            return int(top_bottom.group(1))
        match = re.search(r"(\d+)\s*(?:개|건|줄|행)", text)
        return int(match.group(1)) if match else None

    def _collect_missing_information(self, intent: QueryIntent, text: str, known_fields: list[str]) -> None:
        if intent.source_type == "table" and not intent.tables:
            intent.missing_information.append("조회할 로그프레소 테이블 이름")
        if intent.source_type == "stream" and not intent.streams:
            intent.missing_information.append("조회할 스트림 이름")
        if intent.source_type == "logger" and not intent.loggers:
            intent.missing_information.append("조회할 로그 수집기 이름")
        if intent.source_type == "logger" and not intent.logger_window:
            intent.missing_information.append("실시간 조회 기간")
        if intent.source_type == "file" and not intent.file_path:
            intent.missing_information.append("조회할 파일 경로")
        if intent.source_type == "file" and intent.file_path and not intent.file_command:
            intent.missing_information.append("파일 형식에 맞는 명령")
        if intent.source_type == "file" and intent.file_path and any(char.isspace() for char in intent.file_path):
            intent.missing_information.append("공백 없는 파일 경로")
        if intent.file_command == "zipfile" and not intent.archive_member:
            intent.missing_information.append("ZIP 내부에서 조회할 파일 이름")
        if intent.source_type == "fulltext" and not intent.fulltext_expression:
            intent.missing_information.append("전체 텍스트 검색어")
        if intent.source_type != "fulltext" and any(word in text for word in ERROR_WORDS + DENY_WORDS) and not intent.filters:
            intent.missing_information.append("필터에 사용할 필드명과 값")
        numeric_filters = intent.filters + intent.post_filters
        if self._looks_like_comparison(text) and not any(filter_.value_type == "number" for filter_ in numeric_filters):
            intent.missing_information.append("비교 조건에 사용할 필드명과 값")
        if intent.source_type != "fulltext" and self._looks_like_string_filter(text) and not intent.filters:
            intent.missing_information.append("필터에 사용할 필드명과 값")
        if intent.source_type != "fulltext" and self._has_mixed_boolean_filter(text):
            intent.missing_information.append("복합 필터 괄호 구조")
        if any(word in text.lower() for word in ("rename", "이름 변경", "이름변경", "필드명 변경")) and not intent.renames:
            intent.missing_information.append("변경할 원본 필드명과 새 필드명")
        if self._looks_like_field_selection(text) and not intent.selected_fields:
            intent.missing_information.append("출력할 필드명")
        if self._looks_like_computation(text) and not intent.computed_fields and not intent.aggregations:
            intent.missing_information.append("계산할 표현식과 새 필드명")
        if self._looks_like_parse(text) and not intent.parser_name and not intent.structured_parser:
            intent.missing_information.append("적용할 파서 이름")
        if self._looks_like_explode(text) and not intent.explode_fields:
            intent.missing_information.append("행으로 확장할 배열 필드명")
        if self._looks_like_metric_aggregation(text) and not intent.aggregations:
            intent.missing_information.append("집계할 필드명")
        if intent.use_parameterized_time_range and not intent.time_range:
            intent.missing_information.append("매개변수로 지정할 조회 기간")
        if self._looks_like_sample_aggregation(text) and not intent.aggregations:
            intent.missing_information.append("대표 로그로 출력할 필드명")
        if ("IP별" in text or "출발지 IP" in text) and not intent.group_by:
            intent.missing_information.append("IP 집계에 사용할 필드명")
        if "사용자" in text and ("별" in text or "사용자의" in text) and not intent.group_by and "root" not in text:
            intent.missing_information.append("사용자 집계에 사용할 필드명")
        if not intent.time_range and any(word in text for word in ("최근", "지난", "동안", "대량", "전체", "모든")):
            intent.missing_information.append("조회 기간")
        if intent.source_type == "fulltext" and not intent.tables and not intent.time_range:
            intent.missing_information.append("조회 기간")
        if not intent.limit and not intent.time_range and any(word in text for word in ("전체", "모든", "대량", "제한 없이")):
            intent.missing_information.append("출력 건수 제한")
        if known_fields and intent.aggregations and any(word in text for word in ("IP별", "사용자별")) and not intent.group_by:
            intent.missing_information.append("그룹 기준 필드명")
        if self._looks_like_ratio(text) and not intent.group_by:
            intent.missing_information.append("그룹 기준 필드명")
        if self._looks_like_unique_values(text) and not intent.group_by:
            intent.missing_information.append("그룹 기준 필드명")
        intent.missing_information = list(dict.fromkeys(intent.missing_information))

    def _has_mixed_boolean_filter(self, text: str) -> bool:
        lowered = text.lower()
        has_or = any(word in lowered for word in ("또는", "혹은", "이거나", "거나", " or "))
        has_and = any(word in lowered for word in ("그리고", "이면서", "동시에", " 및 ", " and "))
        if not (has_or and has_and):
            return False
        if text.count("(") != text.count(")"):
            return True
        groups = self._parenthesized_or_groups(text)
        if not groups:
            return True
        if any(any(word in group.lower() for word in ("그리고", "이면서", "동시에", " 및 ", " and ")) for group in groups):
            return True
        outside = text
        for group in groups:
            outside = outside.replace(f"({group})", "")
        return any(word in outside.lower() for word in ("또는", "혹은", "이거나", "거나", " or "))

    def _looks_like_comparison(self, text: str) -> bool:
        return any(word in text for word in ("이상", "초과", "이하", "미만", ">=", "<=", ">", "<"))

    def _looks_like_parse(self, text: str) -> bool:
        return bool(re.search(r"\bparse\b", text, flags=re.IGNORECASE) or any(word in text for word in ("파서", "파싱")))

    def _looks_like_explode(self, text: str) -> bool:
        return any(word in text.lower() for word in ("explode", "배열을 펼", "배열 필드", "행으로 확장", "원소별 행"))

    def _looks_like_string_filter(self, text: str) -> bool:
        return bool(
            re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*(?:가|이|은|는)\s*[가-힣A-Za-z0-9_.:/-]+\s*(?:인|아닌|같은)", text)
            or re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*(?:==|=|!=)\s*[가-힣A-Za-z0-9_.:/-]+", text)
            or re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*(?:에|에서|이|가|은|는)?\s*[가-힣A-Za-z0-9_.:/-]+\s*(?:문자열을\s*)?(?:포함|contains)", text)
        )

    def _looks_like_metric_aggregation(self, text: str) -> bool:
        return any(word in text for word in AGGREGATION_WORDS)

    def _looks_like_ratio(self, text: str) -> bool:
        return any(word in text.lower() for word in ("비율", "퍼센트", "percent", "percentage", "ratio", "%"))

    def _looks_like_unique_values(self, text: str) -> bool:
        lowered = text.lower()
        return any(word in lowered for word in ("고유", "중복 제거", "중복제거", "unique", "distinct"))

    def _looks_like_unique_count(self, text: str) -> bool:
        lowered = text.lower()
        return self._looks_like_unique_values(text) and any(word in lowered for word in ("개수", "건수", "count", "카운트"))

    def _looks_like_fulltext(self, text: str) -> bool:
        lowered = text.lower()
        all_sources = any(word in text for word in ("전체 테이블", "모든 테이블", "전체 로그", "모든 로그"))
        search_cue = any(word in text for word in ("검색", "찾아", "포함"))
        return "fulltext" in lowered or (all_sources and search_cue)

    def _looks_like_parameterized_time_range(self, text: str) -> bool:
        return any(word in text for word in ("매개변수", "파라미터", "동적", "동적으로"))

    def _looks_like_sample_aggregation(self, text: str) -> bool:
        sample_target = any(word in text for word in ("로그", "이벤트", "레코드", "샘플"))
        sample_word = any(word in text for word in ("첫 번째", "첫번째", "처음", "대표", "샘플", "마지막", "최신"))
        return sample_target and sample_word

    def _sample_function(self, text: str) -> str:
        if any(word in text for word in ("마지막", "최신")):
            return "last"
        return "first"

    def _sample_field(self, known_fields: list[str]) -> str | None:
        for candidate in SAMPLE_FIELD_CANDIDATES:
            if candidate in known_fields:
                return candidate
        return None

    def _alias_field(self, field: str) -> str:
        return field.lstrip("_") or field
