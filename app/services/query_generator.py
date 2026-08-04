from __future__ import annotations

import json
import re

from app.core.config import settings
from app.models.request import GenerateQueryRequest, QueryIntent
from app.models.response import GenerateQueryResponse, QueryExplanation
from app.services.citation_service import references_for_query_parts, references_from_results
from app.services.intent_parser import IntentParser
from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever


class QueryGenerator:
    def __init__(self, retriever: Retriever, llm: LLMProvider | None = None):
        self.retriever = retriever
        self.intent_parser = IntentParser()
        self.validator = QueryValidator(retriever)
        self.llm = llm or self._provider()

    def generate(self, payload: GenerateQueryRequest) -> GenerateQueryResponse:
        intent = self.intent_parser.parse(payload)
        search_text = f"{payload.request} table logger stream fulltext evtx-file eml-file lnk-file search parse explode stats rollup timechart eval fields rename first last set setq"
        results = self.retriever.search(search_text, limit=settings.retrieval_limit)
        if not results:
            return GenerateQueryResponse(
                status="unsupported",
                query=None,
                intent=intent,
                questions=[],
                debug={"reason": "문서 인덱스에 검색 결과가 없습니다. /documents/reindex를 실행하십시오."},
            )
        if intent.missing_information:
            return GenerateQueryResponse(
                status="needs_clarification",
                query=None,
                questions=self._questions(intent),
                intent=intent,
                references=references_from_results(results[:3], "확인 질문을 만들기 위해 관련 문법을 검색했습니다."),
                debug={"retrieved": len(results)},
            )

        prompt = self._generation_prompt(payload, intent, results)
        llm_data = self.llm.generate_json(prompt, results)
        llm_query = self._query_from_llm(llm_data)
        query = llm_query or self._template_query(intent)
        validation = self.validator.validate(query)
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
            repaired_validation = self.validator.validate(repaired)
            query = repaired
            validation = repaired_validation
        used_template_fallback = False
        if not validation.valid and llm_query:
            template_query = self._safe_template_query(intent)
            template_validation = self.validator.validate(template_query)
            if template_validation.valid:
                query = template_query
                validation = template_validation
                used_template_fallback = True
        references = references_for_query_parts(
            self.retriever,
            query,
            "생성된 쿼리에 실제 사용된 명령어의 문서 근거입니다.",
        )
        return GenerateQueryResponse(
            status="generated" if validation.valid else "unsupported",
            query=query if validation.valid else None,
            intent=intent,
            validation=validation,
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

    def _safe_template_query(self, intent: QueryIntent) -> str:
        try:
            return self._template_query(intent)
        except ValueError:
            return ""

    def _template_query(self, intent: QueryIntent) -> str:
        if intent.source_type == "fulltext":
            return self._fulltext_query(intent)
        if intent.source_type == "logger":
            return self._logger_query(intent)
        if intent.source_type == "stream":
            return self._stream_query(intent)
        if intent.source_type == "file":
            return self._file_query(intent)
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
        if intent.parser_name:
            lines.append(f"| parse {intent.parser_name}")
        lines.extend(self._filter_lines(intent))
        for computed in intent.computed_fields:
            lines.append(f"| eval {computed.name} = {computed.expression}")
        for field in intent.explode_fields:
            lines.append(f"| explode {field}")
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
        return "\n".join(lines)

    def _logger_query(self, intent: QueryIntent) -> str:
        if not intent.loggers or not intent.logger_window:
            raise ValueError("logger name and window are required to generate a logger query")
        lines = [f"logger window={intent.logger_window} {', '.join(intent.loggers)}"]
        if intent.parser_name:
            lines.append(f"| parse {intent.parser_name}")
        lines.extend(self._filter_lines(intent))
        lines.extend(f"| explode {field}" for field in intent.explode_fields)
        return "\n".join(lines)

    def _stream_query(self, intent: QueryIntent) -> str:
        if not intent.streams:
            raise ValueError("stream name is required to generate a stream query")
        command = "stream"
        if intent.stream_window:
            command += f" window={intent.stream_window}"
        lines = [f"{command} {', '.join(intent.streams)}"]
        if intent.parser_name:
            lines.append(f"| parse {intent.parser_name}")
        lines.extend(self._filter_lines(intent))
        lines.extend(f"| explode {field}" for field in intent.explode_fields)
        return "\n".join(lines)

    def _file_query(self, intent: QueryIntent) -> str:
        if not intent.file_command or not intent.file_path:
            raise ValueError("documented file command and path are required to generate a file query")
        lines = [f"{intent.file_command} {intent.file_path}"]
        if intent.parser_name:
            lines.append(f"| parse {intent.parser_name}")
        lines.extend(self._filter_lines(intent))
        lines.extend(f"| explode {field}" for field in intent.explode_fields)
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
        if intent.limit:
            command += f" limit={intent.limit}"
        command += f" {self._format_fulltext_expression(intent.fulltext_expression)}"
        if intent.tables:
            command += f" from {', '.join(intent.tables)}"
        return command

    def _post_filter_lines(self, intent: QueryIntent) -> list[str]:
        lines: list[str] = []
        for filter_ in intent.post_filters:
            lines.append(f"| search {self._format_filter_expression(filter_)}")
        return lines

    def _filter_lines(self, intent: QueryIntent) -> list[str]:
        lines: list[str] = []
        group = []
        for filter_ in intent.filters:
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
            "조회할 로그 수집기 이름": "조회할 로그 수집기 이름을 네임스페이스와 함께 알려주세요. 예: local\\sample1",
            "실시간 조회 기간": "로그 수집기를 실시간으로 조회할 기간은 얼마인가요? 예: 10초",
            "조회할 파일 경로": "조회할 파일의 전체 경로는 무엇인가요?",
            "파일 형식에 맞는 명령": "파일 형식을 확인할 수 없습니다. 지원할 파일 종류와 경로를 알려주세요.",
            "공백 없는 파일 경로": "문서에서 공백 포함 경로의 인용 문법을 확인하지 못했습니다. 공백이 없는 경로를 알려주세요.",
            "적용할 파서 이름": "적용할 로그프레소 파서 이름은 무엇인가요? 예: openssh",
            "행으로 확장할 배열 필드명": "배열 원소마다 행으로 확장할 필드명은 무엇인가요? 예: tags",
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
        }
        return [mapping[item] for item in intent.missing_information if item in mapping] or [
            "쿼리 생성을 위해 부족한 조건을 알려주세요."
        ]

    def _format_filter_value(self, filter_) -> str:
        if filter_.value_type == "number":
            return str(filter_.value)
        return f'"{filter_.value}"'

    def _quote_fulltext_expression(self, expression: str) -> str:
        escaped = expression.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _format_fulltext_expression(self, expression: str) -> str:
        number = r"-?\d+(?:\.\d+)?"
        ipv4 = r"(?:\d{1,3}\.){3}\d{1,3}"
        if re.fullmatch(rf"range\({number},\s*{number}\)", expression):
            return expression
        if re.fullmatch(rf'iprange\("{ipv4}",\s*"{ipv4}"\)', expression):
            return expression
        boolean_tokens = re.sub(r'"(?:[^"\\]|\\.)*"|\band\b|\bor\b|[()\s]', "", expression)
        if not boolean_tokens and re.search(r'"', expression):
            return expression
        return self._quote_fulltext_expression(expression)

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
            elif line.startswith("logger"):
                explanations.append(QueryExplanation(query_part=line, reason="지정한 로그 수집기의 데이터를 정해진 기간 동안 실시간으로 조회합니다."))
            elif line.startswith("stream"):
                explanations.append(QueryExplanation(query_part=line, reason="지정한 스트림에서 실시간 데이터를 수신합니다."))
            elif re.match(r"^(?:evtx|eml|lnk)-file\b", line):
                explanations.append(QueryExplanation(query_part=line, reason="파일 형식에 맞는 문서 기반 명령으로 파일 내용을 조회합니다."))
            elif line.startswith("| search"):
                explanations.append(QueryExplanation(query_part=line, reason="사용자 요청에서 추출한 필터 조건을 적용합니다."))
            elif line.startswith("| eval"):
                explanations.append(QueryExplanation(query_part=line, reason="요청한 계산식을 새 필드로 생성합니다."))
            elif line.startswith("| parse"):
                explanations.append(QueryExplanation(query_part=line, reason="문서에 정의된 parse 명령으로 지정한 파서를 적용합니다."))
            elif line.startswith("| explode"):
                explanations.append(QueryExplanation(query_part=line, reason="배열 필드의 각 원소를 개별 행으로 확장합니다."))
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
