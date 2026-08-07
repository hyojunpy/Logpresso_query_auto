from __future__ import annotations

import json
import re

from app.core.config import settings
from app.models.request import GenerateQueryRequest, QueryIntent
from app.models.response import ExecutionPreview, GenerateQueryResponse, QueryExplanation
from app.services.citation_service import references_for_query_parts, references_from_results
from app.services.intent_parser import DENY_WORDS, ERROR_WORDS, IntentParser
from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever
from app.services.catalog_service import CatalogService
from app.services.execution_preview import ExecutionPreviewService
from app.services.quality_analyzer import QueryQualityAnalyzer
from app.services.alias_store import AliasStore


class QueryGenerator:
    def __init__(self, retriever: Retriever, llm: LLMProvider | None = None):
        self.retriever = retriever
        self.intent_parser = IntentParser()
        self.validator = QueryValidator(retriever)
        self.catalog = CatalogService(settings.catalog_path)
        self.quality_analyzer = QueryQualityAnalyzer()
        self.execution_preview = ExecutionPreviewService()
        self.llm = llm or self._provider()

    def generate(self, payload: GenerateQueryRequest) -> GenerateQueryResponse:
        payload = self._with_business_aliases(payload)
        intent = self.intent_parser.parse(payload)
        search_text = f"{payload.request} table logger stream fulltext search stats rollup timechart eval fields rename join first last set setq"
        results = self.retriever.search(search_text, limit=settings.retrieval_limit)
        if not results:
            return GenerateQueryResponse(
                status="unsupported",
                query=None,
                intent=intent,
                questions=[],
                execution_preview=ExecutionPreview(
                    status="unsupported", is_read_only=None, risk_level="high",
                    blocked_reasons=["문서 인덱스 결과가 없어 쿼리를 생성할 수 없습니다."],
                ),
                debug={"reason": "문서 인덱스에 검색 결과가 없습니다. /documents/reindex를 실행하십시오."},
            )
        if intent.missing_information:
            assisted = self._llm_intent_fallback(payload, intent, results)
            if assisted is not None:
                return assisted
            return GenerateQueryResponse(
                status="needs_clarification",
                query=None,
                questions=self._questions(intent),
                intent=intent,
                execution_preview=ExecutionPreview(
                    status="not_requested", is_read_only=None, risk_level="low",
                    confirmation_message="확인 질문에 답한 뒤 쿼리 생성과 검증을 진행하세요.",
                ),
                references=references_from_results(results[:3], "확인 질문을 만들기 위해 관련 문법을 검색했습니다."),
                debug={"retrieved": len(results)},
            )

        prompt = self._generation_prompt(payload, intent, results)
        llm_data = self.llm.generate_json(prompt, results)
        llm_query = self._query_from_llm(llm_data)
        query = llm_query or self._template_query(intent)
        validation = self._validate(query, payload)
        repair_attempts = 0
        while not validation.valid and repair_attempts < 2:
            repair_attempts += 1
            repaired_data = self.llm.repair_json(
                self._repair_prompt(query, validation.errors, results),
                query,
                validation.errors,
                results,
            )
            repaired = self._query_from_llm(repaired_data)
            if not repaired or repaired == query:
                break
            repaired_validation = self._validate(repaired, payload)
            query = repaired
            validation = repaired_validation
        used_template_fallback = False
        if not validation.valid and llm_query:
            template_query = self._safe_template_query(intent)
            template_validation = self._validate(template_query, payload)
            if template_validation.valid:
                query = template_query
                validation = template_validation
                used_template_fallback = True
        references = references_for_query_parts(
            self.retriever,
            query,
            "생성된 쿼리에 실제 사용된 명령어의 문서 근거입니다.",
        )
        quality = self.quality_analyzer.analyze(query, validation)
        preview = self.execution_preview.build(query if validation.valid else None, validation, quality)
        return GenerateQueryResponse(
            status="generated" if validation.valid else "unsupported",
            query=query if validation.valid else None,
            intent=intent,
            validation=validation,
            schema_validation=self.catalog.validate_query(query, payload.context),
            quality=quality,
            execution_preview=preview,
            explanation=self._explain(query),
            references=references or references_from_results(results, "생성된 쿼리의 명령어와 옵션 근거입니다."),
            assumptions=intent.assumptions,
            debug={
                "provider": settings.llm_provider,
                "retrieved": len(results),
                "reference_mode": "commands" if references else "retrieval_fallback",
                "llm_status": llm_data.get("status"),
                "llm_used": bool(llm_query) and not used_template_fallback,
                "template_fallback": used_template_fallback,
                "repair_attempts": repair_attempts,
            },
        )

    @staticmethod
    def _with_business_aliases(payload: GenerateQueryRequest) -> GenerateQueryRequest:
        context = payload.context.model_copy(deep=True)
        additions: list[str] = []
        try:
            aliases = AliasStore(settings.db_path).list()
        except Exception:
            return payload
        for alias in aliases:
            if alias["phrase"].lower() not in payload.request.lower():
                continue
            if alias["kind"] == "table" and alias["target"] not in context.known_tables:
                context.known_tables.append(alias["target"])
                additions.append(f"{alias['target']} 테이블")
            elif alias["kind"] == "field" and alias["target"] not in context.known_fields:
                context.known_fields.append(alias["target"])
        if not additions:
            return payload.model_copy(update={"context": context})
        return payload.model_copy(update={"request": payload.request + "\n" + " ".join(additions), "context": context})

    def _validate(self, query: str, payload: GenerateQueryRequest):
        syntax = self.validator.validate(query)
        schema = self.catalog.validate_query(query, payload.context)
        syntax.errors.extend(schema.errors)
        syntax.warnings.extend(schema.warnings)
        syntax.compatibility_notes.extend(schema.compatibility_notes)
        syntax.valid = not syntax.errors
        return syntax

    def _llm_intent_fallback(self, payload: GenerateQueryRequest, intent: QueryIntent, results):
        """Use an enabled real LLM only when deterministic intent extraction needs help."""
        if not settings.enable_llm_intent_fallback or settings.llm_provider == "mock":
            return None

        data = self.llm.generate_json(self._intent_resolution_prompt(payload, intent, results), results)
        query = self._query_from_llm_intent(data, intent, payload)
        if not query:
            return None

        validation = self._validate(query, payload)
        if not validation.valid:
            return None

        references = references_for_query_parts(
            self.retriever,
            query,
            "LLM-assisted query commands were matched to the indexed documentation.",
        )
        quality = self.quality_analyzer.analyze(query, validation)
        preview = self.execution_preview.build(query, validation, quality)
        assumptions = [*intent.assumptions, "Query structure was resolved by the LLM and passed local validation."]
        llm_assumptions = data.get("assumptions")
        if isinstance(llm_assumptions, list):
            assumptions.extend(value for value in llm_assumptions if isinstance(value, str))
        return GenerateQueryResponse(
            status="generated",
            query=query,
            intent=intent,
            validation=validation,
            schema_validation=self.catalog.validate_query(query, payload.context),
            quality=quality,
            execution_preview=preview,
            explanation=self._explain(query),
            references=references or references_from_results(results, "LLM-assisted query context."),
            assumptions=list(dict.fromkeys(assumptions)),
            debug={
                "provider": settings.llm_provider,
                "retrieved": len(results),
                "llm_status": data.get("status"),
                "llm_used": True,
                "llm_intent_fallback": True,
                "template_fallback": False,
                "repair_attempts": 0,
            },
        )

    @staticmethod
    def _query_from_llm_intent(data: dict, intent: QueryIntent, payload: GenerateQueryRequest) -> str | None:
        if data.get("status") != "generated":
            return None
        table = data.get("table")
        allowed_tables = set(intent.tables)
        catalog = payload.context.catalog or payload.context.request_catalog
        if catalog:
            allowed_tables.update(item.table_name for item in catalog.tables)
        if not isinstance(table, str) or table not in allowed_tables:
            return None

        duration = data.get("duration")
        if not isinstance(duration, str) or not re.fullmatch(r"\d+[smhdw]", duration):
            duration = intent.time_range.duration if intent.time_range and intent.time_range.duration else None
        if not duration:
            return None

        lines = [f"table duration={duration} {table}"]
        filter_field = data.get("filter_field")
        filter_value = data.get("filter_value")
        requires_filter = any(word.lower() in intent.objective.lower() for word in ERROR_WORDS + DENY_WORDS)
        if requires_filter and not (isinstance(filter_field, str) and isinstance(filter_value, str)):
            return None
        if isinstance(filter_field, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", filter_field) and isinstance(filter_value, str):
            lines.append(f'| search {filter_field} == "{filter_value.replace(chr(34), chr(92) + chr(34))}"')

        group_by = data.get("group_by")
        if isinstance(group_by, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", group_by):
            lines.append(f"| stats count by {group_by}")
        else:
            lines.append("| stats count")

        if data.get("sort_desc", True):
            lines.append("| sort -count")
        limit = data.get("limit")
        if not isinstance(limit, int) or not 1 <= limit <= 10000:
            limit = intent.limit
        if isinstance(limit, int):
            lines.append(f"| limit {limit}")
        return "\n".join(lines)

    def _safe_template_query(self, intent: QueryIntent) -> str:
        try:
            return self._template_query(intent)
        except ValueError:
            return ""

    def _template_query(self, intent: QueryIntent) -> str:
        if intent.join:
            return self._join_query(intent.join, intent)
        if intent.source_type == "logger":
            return self._realtime_query("logger", intent.loggers, intent)
        if intent.source_type == "stream":
            return self._realtime_query("stream", intent.streams, intent)
        if intent.source_type == "fulltext":
            return self._fulltext_query(intent)
        if not intent.tables:
            raise ValueError("table is required to generate a table query")
        if intent.use_parameterized_time_range:
            return self._parameterized_table_query(intent)
        table = intent.tables[0]
        first = "table"
        if intent.time_range and intent.time_range.duration:
            first += f" duration={intent.time_range.duration}"
        elif intent.time_range and intent.time_range.from_ and intent.time_range.to:
            first += f" from={intent.time_range.from_} to={intent.time_range.to}"
        first += f" {table}"
        lines = [first]
        lines.extend(self._filter_lines(intent))
        for computed in intent.computed_fields:
            lines.append(f"| eval {computed.name} = {computed.expression}")
        for rename in intent.renames:
            lines.append(f"| rename {rename.field} as {rename.new_name}")
        if intent.selected_fields:
            lines.append(f"| fields {', '.join(intent.selected_fields)}")
        if intent.aggregations:
            if self._time_span(intent):
                lines.append(f"| timechart span={self._time_span(intent)} {self._format_aggregations(intent)}")
            elif intent.group_by:
                lines.append(
                    f"| {intent.aggregation_command} {self._format_aggregations(intent)} by {', '.join(intent.group_by)}"
                )
            else:
                lines.append(f"| stats {self._format_aggregations(intent)}")
        if intent.final_aggregations:
            lines.append(f"| stats {self._format_aggregation_list(intent.final_aggregations)}")
        lines.extend(self._post_filter_lines(intent))
        for sort in intent.sort:
            prefix = "-" if sort.direction == "desc" else ""
            lines.append(f"| sort {prefix}{sort.field}")
        if intent.limit:
            lines.append(f"| limit {intent.limit}")
        if intent.forward_streams:
            lines.append(f"| stream forward=t {', '.join(intent.forward_streams)}")
        return "\n".join(lines)

    def _realtime_query(self, command: str, sources: list[str], intent: QueryIntent) -> str:
        if not sources:
            raise ValueError(f"{command} source is required")
        if not intent.time_range or not intent.time_range.duration:
            raise ValueError("duration is required for a realtime query")
        lines = [f"{command} window={intent.time_range.duration} {', '.join(sources)}"]
        lines.extend(self._filter_lines(intent))
        for computed in intent.computed_fields:
            lines.append(f"| eval {computed.name} = {computed.expression}")
        for rename in intent.renames:
            lines.append(f"| rename {rename.field} as {rename.new_name}")
        if intent.selected_fields:
            lines.append(f"| fields {', '.join(intent.selected_fields)}")
        if intent.aggregations:
            if self._time_span(intent):
                lines.append(f"| timechart span={self._time_span(intent)} {self._format_aggregations(intent)}")
            elif intent.group_by:
                lines.append(f"| {intent.aggregation_command} {self._format_aggregations(intent)} by {', '.join(intent.group_by)}")
            else:
                lines.append(f"| stats {self._format_aggregations(intent)}")
        if intent.final_aggregations:
            lines.append(f"| stats {self._format_aggregation_list(intent.final_aggregations)}")
        lines.extend(self._post_filter_lines(intent))
        for sort in intent.sort:
            prefix = "-" if sort.direction == "desc" else ""
            lines.append(f"| sort {prefix}{sort.field}")
        if intent.limit:
            lines.append(f"| limit {intent.limit}")
        return "\n".join(lines)

    def _join_query(self, join, intent: QueryIntent) -> str:
        left_name = join.left_rename or join.left_key
        right_name = join.right_rename or join.right_key
        if join.left_source_type in {"stream", "logger"}:
            if not intent.time_range or not intent.time_range.duration:
                raise ValueError("duration is required for a realtime join")
            lines = [f"{join.left_source_type} window={intent.time_range.duration} {join.left_table}"]
        else:
            left_source = "table"
            if intent.time_range and intent.time_range.duration:
                left_source += f" duration={intent.time_range.duration}"
            elif intent.time_range and intent.time_range.from_ and intent.time_range.to:
                left_source += f" from={intent.time_range.from_} to={intent.time_range.to}"
            lines = [f"{left_source} {join.left_table}"]
        lines.extend(self._filter_lines_for(join.left_filters))
        if join.left_rename:
            lines.append(f"| rename {join.left_key} as {join.left_rename}")
        lines.append(f"| eval {join.helper_key} = {left_name}")
        lines.extend([
            f"| {join.command} type={join.join_type} {join.helper_key} [",
            f"    table {join.right_table}",
        ])
        if join.right_rename:
            lines.append(f"    | rename {join.right_key} as {join.right_rename}")
        lines.extend(f"    {line}" for line in self._filter_lines_for(join.right_filters))
        lines.extend([
            f"    | eval {join.helper_key} = {right_name}",
            "]",
        ])
        lines.extend(self._filter_lines(intent))
        for computed in intent.computed_fields:
            lines.append(f"| eval {computed.name} = {computed.expression}")
        if intent.selected_fields:
            lines.append(f"| fields {', '.join(intent.selected_fields)}")
        if intent.aggregations:
            if intent.group_by:
                lines.append(f"| {intent.aggregation_command} {self._format_aggregations(intent)} by {', '.join(intent.group_by)}")
            else:
                lines.append(f"| stats {self._format_aggregations(intent)}")
        for sort in intent.sort:
            prefix = "-" if sort.direction == "desc" else ""
            lines.append(f"| sort {prefix}{sort.field}")
        if intent.limit:
            lines.append(f"| limit {intent.limit}")
        return "\n".join(lines)

    def _parameterized_table_query(self, intent: QueryIntent) -> str:
        if not intent.tables:
            raise ValueError("table is required to generate a parameterized table query")
        if not intent.time_range or not intent.time_range.duration:
            raise ValueError("duration is required to generate a parameterized time range query")
        lines = [
            f'set from=ago("{intent.time_range.duration}")',
            "| set to=str(now())",
            f'| table from=$("from") to=$("to") {intent.tables[0]}',
        ]
        return "\n".join(lines)

    def _fulltext_query(self, intent: QueryIntent) -> str:
        if not intent.fulltext_expression:
            raise ValueError("fulltext expression is required to generate a fulltext query")
        command = "fulltext"
        if intent.time_range and intent.time_range.duration:
            command += f" duration={intent.time_range.duration}"
        elif intent.time_range and intent.time_range.from_ and intent.time_range.to:
            command += f" from={self._fulltext_time(intent.time_range.from_)} to={self._fulltext_time(intent.time_range.to)}"
        if intent.limit and not intent.aggregations:
            command += f" limit={intent.limit}"
        command += f" {self._quote_fulltext_expression(intent.fulltext_expression)}"
        if intent.tables:
            command += f" from {', '.join(intent.tables)}"
        lines = [command]
        lines.extend(self._filter_lines(intent))
        for computed in intent.computed_fields:
            lines.append(f"| eval {computed.name} = {computed.expression}")
        for rename in intent.renames:
            lines.append(f"| rename {rename.field} as {rename.new_name}")
        if intent.selected_fields:
            lines.append(f"| fields {', '.join(intent.selected_fields)}")
        if intent.aggregations:
            if self._time_span(intent):
                lines.append(f"| timechart span={self._time_span(intent)} {self._format_aggregations(intent)}")
            elif intent.group_by:
                lines.append(f"| {intent.aggregation_command} {self._format_aggregations(intent)} by {', '.join(intent.group_by)}")
            else:
                lines.append(f"| stats {self._format_aggregations(intent)}")
        lines.extend(self._post_filter_lines(intent))
        for sort in intent.sort:
            prefix = "-" if sort.direction == "desc" else ""
            lines.append(f"| sort {prefix}{sort.field}")
        if intent.limit and intent.aggregations:
            lines.append(f"| limit {intent.limit}")
        return "\n".join(lines)

    def _post_filter_lines(self, intent: QueryIntent) -> list[str]:
        lines: list[str] = []
        for filter_ in intent.post_filters:
            lines.append(f"| search {self._format_filter_expression(filter_)}")
        return lines

    def _filter_lines(self, intent: QueryIntent) -> list[str]:
        return self._filter_lines_for(intent.filters)

    def _filter_lines_for(self, filters) -> list[str]:
        lines: list[str] = []
        group = []
        for filter_ in filters:
            if filter_.conjunction == "or" and group:
                group.append(filter_)
                continue
            if group:
                lines.append(f"| search {self._format_filter_group(group)}")
            group = [filter_]
        if group:
            lines.append(f"| search {self._format_filter_group(group)}")
        return lines

    def _format_filter_group(self, filters) -> str:
        expression = self._format_filter_expression(filters[0])
        for filter_ in filters[1:]:
            expression += f" {filter_.conjunction} {self._format_filter_expression(filter_)}"
        return expression

    def _format_filter_expression(self, filter_) -> str:
        return f"{filter_.field} {filter_.operator} {self._format_filter_value(filter_)}"

    def _format_aggregations(self, intent: QueryIntent) -> str:
        return self._format_aggregation_list(intent.aggregations)

    def _format_aggregation_list(self, aggregations) -> str:
        expressions = []
        for aggregation in aggregations:
            if aggregation.function == "count":
                expression = "count"
            elif aggregation.field:
                expression = f"{aggregation.function}({aggregation.field})"
            else:
                expression = aggregation.function
            if aggregation.alias:
                expression += f" as {aggregation.alias}"
            expressions.append(expression)
        return ", ".join(expressions)

    def _time_span(self, intent: QueryIntent) -> str | None:
        objective = intent.objective
        unit_map = {"초": "s", "분": "m", "시간": "h", "시": "h", "일": "d", "주": "w"}
        match = re.search(r"(\d+)\s*(초|분|시간|시|일|주)\s*(?:단위|간격)", objective)
        if match:
            return f"{match.group(1)}{unit_map[match.group(2)]}"
        if "10분 단위" in objective or "10분단위" in objective:
            return "10m"
        if "5분 단위" in objective or "5분단위" in objective:
            return "5m"
        if "1시간 단위" in objective or "시간 단위" in objective:
            return "1h"
        return None

    def _questions(self, intent: QueryIntent) -> list[str]:
        mapping = {
            "조회할 로그프레소 테이블 이름": "조회할 로그프레소 테이블 이름은 무엇인가요?",
            "조회할 스트림 이름": "조회할 스트림 이름은 무엇인가요?",
            "필터에 사용할 필드명과 값": "필터에 사용할 필드명과 값은 무엇인가요?",
            "비교 조건에 사용할 필드명과 값": "비교 조건에 사용할 필드명과 값은 무엇인가요? 예: kernel + user가 80 이상",
            "IP 집계에 사용할 필드명": "IP 집계에 사용할 필드명은 무엇인가요? 예: src_ip",
            "사용자 집계에 사용할 필드명": "사용자 집계에 사용할 필드명은 무엇인가요? 예: login_name",
            "조회 기간": "조회 기간은 어떻게 지정할까요? 예: 최근 24시간, 지난 7일",
            "출력 건수 제한": "출력 건수 제한은 몇 건으로 할까요?",
            "그룹 기준 필드명": "그룹 기준으로 사용할 필드명은 무엇인가요?",
            "변경할 원본 필드명과 새 필드명": "변경할 원본 필드명과 새 필드명은 무엇인가요? 예: src_ip를 할당ip로",
            "출력할 필드명": "출력할 필드명은 무엇인가요? 예: src_ip, action",
            "계산할 표현식과 새 필드명": "계산할 표현식과 새 필드명은 무엇인가요? 예: kernel + user를 total로",
            "집계할 필드명": "집계할 필드명은 무엇인가요? 예: bytes 평균, elapsed 최대",
            "대표 로그로 출력할 필드명": "대표 로그로 출력할 필드명은 무엇인가요? 예: line 또는 message",
            "전체 텍스트 검색어": "전체 텍스트로 검색할 문자열이나 IP는 무엇인가요? 예: 1.2.3.4",
            "매개변수로 지정할 조회 기간": "매개변수로 지정할 조회 기간은 무엇인가요? 예: 최근 7일",
            "left/right 조인할 두 테이블과 각 조인 키 필드": "조인할 두 테이블과 왼쪽/오른쪽 조인 키를 알려주세요. 예: firewall_logs.src_ip와 firewall_djt.dst_ip",
            "조회할 logger 이름": "조회할 logger 이름을 알려주세요. 예: local\\sample_logger",
            "실시간 조회 기간": "실시간 조회 기간을 알려주세요. 예: 최근 10초 또는 최근 5분",
        }
        return [mapping[item] for item in intent.missing_information if item in mapping] or [
            "쿼리 생성을 위해 부족한 조건을 알려주세요."
        ]

    def _format_filter_value(self, filter_) -> str:
        if filter_.value_type == "number":
            return str(filter_.value)
        return f'"{filter_.value}"'

    def _quote_fulltext_expression(self, expression: str) -> str:
        if expression.startswith('"') and any(operator in expression.lower() for operator in (" and ", " or ")):
            return expression
        escaped = expression.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _fulltext_time(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        return digits[:14]

    def _generation_prompt(self, payload: GenerateQueryRequest, intent: QueryIntent, results) -> str:
        context = [
            {
                "entry_name": result.entry_name,
                "section": result.section,
                "content_type": result.content_type,
                "excerpt": result.excerpt,
                "options": result.options,
                "functions": result.functions,
            }
            for result in results
        ]
        body = {
            "task": "Generate a Logpresso query as JSON. Use only the provided manual context.",
            "request": payload.request,
            "intent": intent.model_dump(by_alias=True),
            "context": context,
            "required_json_schema": {
                "status": "generated|needs_clarification|unsupported",
                "query": "string or null",
                "clarifying_questions": ["string"],
                "assumptions": ["string"],
            },
        }
        return json.dumps(body, ensure_ascii=False, indent=2)

    def _intent_resolution_prompt(self, payload: GenerateQueryRequest, intent: QueryIntent, results) -> str:
        body = {
            "task": (
                "Extract a read-only count query plan. Do not write query syntax. "
                "When the request names a table and a clear result, return generated. "
                "Infer fields only when strongly indicated and record each inference in assumptions."
            ),
            "request": payload.request,
            "allowed_tables": intent.tables,
            "table_candidates": intent.table_candidates,
            "detected_duration": intent.time_range.duration if intent.time_range else None,
            "detected_limit": intent.limit,
            "required_semantics": {
                "must_include_error_filter": any(word.lower() in payload.request.lower() for word in ERROR_WORDS),
                "must_include_deny_filter": any(word.lower() in payload.request.lower() for word in DENY_WORDS),
            },
            "semantic_field_hints": {
                "error_or_failure": {"filter_field": "severity", "filter_value": "error"},
                "deny_or_block": {"filter_field": "action", "filter_value": "deny"},
                "account_or_user": ["account_id", "account", "user", "login_name"],
                "source_ip": "src_ip",
                "destination_ip": "dst_ip",
            },
            "catalog_tables": [table.table_name for table in (payload.context.catalog.tables if payload.context.catalog else [])],
            "manual_hints": [
                {
                    "entry_name": result.entry_name,
                    "excerpt": result.excerpt[:180],
                }
                for result in results[:1]
            ],
            "response_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["generated", "needs_clarification", "unsupported"]},
                    "table": {"type": ["string", "null"]},
                    "duration": {"type": ["string", "null"]},
                    "filter_field": {"type": ["string", "null"]},
                    "filter_value": {"type": ["string", "null"]},
                    "group_by": {"type": ["string", "null"]},
                    "limit": {"type": ["integer", "null"]},
                    "sort_desc": {"type": "boolean"},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["status", "table", "duration", "group_by", "sort_desc"],
            },
        }
        return json.dumps(body, ensure_ascii=False, indent=2)

    def _repair_prompt(self, query: str, errors, results) -> str:
        body = {
            "task": "Repair this Logpresso query. Return JSON only. Do not invent unsupported syntax.",
            "query": query,
            "errors": [error.model_dump() for error in errors],
            "context": [
                {
                    "entry_name": result.entry_name,
                    "section": result.section,
                    "excerpt": result.excerpt,
                    "options": result.options,
                    "functions": result.functions,
                }
                for result in results
            ],
            "required_json_schema": {
                "status": "generated|unsupported",
                "query": "string or null",
            },
        }
        return json.dumps(body, ensure_ascii=False, indent=2)

    def _query_from_llm(self, data: dict) -> str | None:
        if data.get("status") != "generated":
            return None
        query = data.get("query")
        if not isinstance(query, str) or not query.strip():
            return None
        return query.strip()

    def _explain(self, query: str) -> list[QueryExplanation]:
        explanations: list[QueryExplanation] = []
        for line in query.splitlines():
            if line.startswith("table"):
                explanations.append(QueryExplanation(query_part=line, reason="지정한 테이블과 조회 기간으로 원본 로그를 읽습니다."))
            elif line.startswith("fulltext"):
                explanations.append(QueryExplanation(query_part=line, reason="지정한 문자열 또는 IP를 전체 텍스트 검색 문법으로 조회합니다."))
            elif line.startswith("| search"):
                explanations.append(QueryExplanation(query_part=line, reason="사용자 요청에서 추출한 필터 조건을 적용합니다."))
            elif line.startswith("| eval"):
                explanations.append(QueryExplanation(query_part=line, reason="요청한 계산식을 새 필드로 생성합니다."))
            elif line.startswith("| rename"):
                explanations.append(QueryExplanation(query_part=line, reason="요청한 원본 필드명을 새 표시 필드명으로 변경합니다."))
            elif line.startswith("| fields"):
                explanations.append(QueryExplanation(query_part=line, reason="요청한 필드만 출력하도록 결과 필드를 선택합니다."))
            elif line.startswith("| stats") or line.startswith("| timechart"):
                explanations.append(QueryExplanation(query_part=line, reason="요청한 건수 집계 또는 시간 단위 집계를 수행합니다."))
            elif line.startswith("| rollup"):
                explanations.append(QueryExplanation(query_part=line, reason="그룹별 집계와 전체 집계를 함께 계산합니다."))
            elif line.startswith("| sort") or line.startswith("| limit"):
                explanations.append(QueryExplanation(query_part=line, reason="정렬 및 출력 건수 조건을 적용합니다."))
        return explanations

    def _provider(self) -> LLMProvider:
        if settings.llm_provider == "openai":
            return OpenAIProvider()
        if settings.llm_provider == "ollama":
            return OllamaProvider()
        return MockProvider()
