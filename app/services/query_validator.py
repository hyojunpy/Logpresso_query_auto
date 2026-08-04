from __future__ import annotations

import re

from app.models.response import ValidationIssue, ValidationResult
from app.services.retriever import Retriever


FUNCTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
OPTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=")
KNOWN_OPTIONS = {
    "table": {"duration", "from", "to", "limit", "offset", "order"},
    "fulltext": {"duration", "from", "to", "limit", "offset", "order", "tt"},
    "timechart": {"span", "offset", "parallel"},
    "rollup": {"label", "parallel"},
    "stream": {"forward", "window"},
    "sort": {"limit"},
}
ADMIN_COMMANDS = {"system", "admin", "delete", "drop", "truncate"}
EXCLUSIVE_TIME_OPTION_COMMANDS = {"table", "fulltext"}


class QueryValidator:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def validate(self, query: str) -> ValidationResult:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        commands = self._commands(query)
        functions = sorted(set(FUNCTION_RE.findall(self._without_quoted_text(query))))

        if not query.strip():
            errors.append(ValidationIssue(code="empty_query", message="빈 쿼리입니다."))
        if self._has_empty_pipeline_segment(query):
            errors.append(ValidationIssue(code="empty_pipeline_segment", message="파이프 사이에 빈 명령문이 있습니다."))
        if not commands:
            errors.append(ValidationIssue(code="missing_command", message="명령어를 찾을 수 없습니다."))
        if not self._balanced(query, "(", ")") or not self._balanced(query, "[", "]"):
            errors.append(ValidationIssue(code="unbalanced_brackets", message="괄호 또는 서브쿼리 괄호가 닫히지 않았습니다."))
        if not self._balanced_quotes(query):
            errors.append(ValidationIssue(code="unbalanced_quotes", message="따옴표 쌍이 닫히지 않았습니다."))

        for command in commands:
            if not self.retriever.command_exists(command):
                errors.append(
                    ValidationIssue(
                        code="unknown_command",
                        message=f"문서 인덱스에서 '{command}' 명령어를 확인하지 못했습니다.",
                        evidence=command,
                    )
                )
        for function in functions:
            if not self.retriever.function_exists(function):
                warnings.append(
                    ValidationIssue(
                        code="unknown_function",
                        message=f"문서 인덱스에서 '{function}' 함수를 확인하지 못했습니다.",
                        evidence=function,
                    )
                )

        command_options = self._command_options(query)
        for command, options in command_options:
            if command in EXCLUSIVE_TIME_OPTION_COMMANDS and {"duration", "from", "to"}.issubset(options):
                errors.append(
                    ValidationIssue(
                        code="exclusive_time_options",
                        message=f"{command} 명령에서 duration과 from/to를 동시에 사용하지 마십시오.",
                        evidence=command,
                    )
                )
        errors.extend(self._required_parameter_errors(query))
        for command, options in command_options:
            allowed = self.retriever.options_for_command(command) or KNOWN_OPTIONS.get(command, set())
            for option in options:
                if allowed and option not in allowed:
                    warnings.append(
                        ValidationIssue(
                            code="unknown_option",
                            message=f"'{command}' 명령에서 '{option}' 옵션 근거를 확인하지 못했습니다.",
                            evidence=option,
                        )
                    )
        if self._has_bad_comment_spacing(query):
            warnings.append(ValidationIssue(code="comment_spacing", message="주석은 '# ' 뒤에 작성하십시오."))

        requires_admin = any(command in ADMIN_COMMANDS for command in commands)
        risk = "high" if requires_admin else ("medium" if any("fulltext" in c for c in commands) else "low")
        if requires_admin:
            warnings.append(ValidationIssue(code="admin_required", message="관리자 권한이 필요할 수 있는 명령어가 포함되었습니다."))
        return ValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            commands=commands,
            functions=functions,
            risk_level=risk,
            requires_admin=requires_admin,
        )

    def _commands(self, query: str) -> list[str]:
        commands: list[str] = []
        for segment in self._pipeline_segments(query):
            stripped = segment.strip()
            if not stripped:
                continue
            command = stripped.split()[0].lower()
            commands.append(command)
        return commands

    def _has_empty_pipeline_segment(self, query: str) -> bool:
        if not query.strip():
            return False
        segments = self._pipeline_segments(query)
        return any(not segment.strip() for segment in segments)

    def _command_options(self, query: str) -> list[tuple[str, set[str]]]:
        command_options: list[tuple[str, set[str]]] = []
        for segment in self._pipeline_segments(query):
            stripped = segment.strip()
            if not stripped:
                continue
            parts = stripped.split(maxsplit=1)
            command = parts[0].lower()
            argument_text = self._without_quoted_text(parts[1] if len(parts) > 1 else "")
            options = {
                option.lower()
                for option in OPTION_RE.findall(argument_text)
            }
            command_options.append((command, options))
        return command_options

    def _required_parameter_errors(self, query: str) -> list[ValidationIssue]:
        errors: list[ValidationIssue] = []
        for segment in self._pipeline_segments(query):
            stripped = segment.strip()
            if not stripped:
                continue
            command = stripped.split(maxsplit=1)[0].lower()
            arguments = self._arguments_without_options(stripped)
            if command == "table" and not arguments:
                errors.append(
                    ValidationIssue(
                        code="missing_required_parameter",
                        message="table 명령에는 조회할 테이블 이름이 필요합니다.",
                        evidence=command,
                    )
                )
            elif command == "fulltext" and (not arguments or arguments.lower().startswith("from ")):
                errors.append(
                    ValidationIssue(
                        code="missing_required_parameter",
                        message="fulltext 명령에는 검색할 문자열 또는 표현식이 필요합니다.",
                        evidence=command,
                    )
                )
            elif command in {"stats", "rollup", "timechart"} and not arguments:
                errors.append(
                    ValidationIssue(
                        code="missing_required_parameter",
                        message=f"{command} 명령에는 집계 함수 또는 표현식이 필요합니다.",
                        evidence=command,
                    )
                )
        return errors

    def _arguments_without_options(self, segment: str) -> str:
        parts = segment.split(maxsplit=1)
        if len(parts) == 1:
            return ""
        rest = parts[1]
        rest = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*=(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|\S+)", " ", rest)
        return re.sub(r"\s+", " ", rest).strip()

    def _pipeline_segments(self, query: str) -> list[str]:
        segments: list[str] = []
        buffer: list[str] = []
        quote: str | None = None
        escaped = False
        bracket_depth = 0
        for char in query:
            if escaped:
                buffer.append(char)
                escaped = False
                continue
            if char == "\\":
                buffer.append(char)
                escaped = True
                continue
            if char in {"'", '"'}:
                buffer.append(char)
                if quote is None:
                    quote = char
                elif quote == char:
                    quote = None
                continue
            if quote is None:
                if char == "[":
                    bracket_depth += 1
                elif char == "]" and bracket_depth > 0:
                    bracket_depth -= 1
                elif char == "|" and bracket_depth == 0:
                    segments.append("".join(buffer))
                    buffer = []
                    continue
            buffer.append(char)
        segments.append("".join(buffer))
        return segments

    def _has_bad_comment_spacing(self, query: str) -> bool:
        quote: str | None = None
        escaped = False
        for line in query.splitlines():
            quote = None
            escaped = False
            for index, char in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char in {"'", '"'}:
                    if quote is None:
                        quote = char
                    elif quote == char:
                        quote = None
                    continue
                if char == "#" and quote is None:
                    next_char = line[index + 1] if index + 1 < len(line) else ""
                    return next_char != " "
        return False

    def _without_quoted_text(self, text: str) -> str:
        output: list[str] = []
        quote: str | None = None
        escaped = False
        for char in text:
            if escaped:
                output.append(" " if quote else char)
                escaped = False
                continue
            if char == "\\":
                output.append(" " if quote else char)
                escaped = True
                continue
            if char in {"'", '"'}:
                output.append(" ")
                if quote is None:
                    quote = char
                elif quote == char:
                    quote = None
                continue
            output.append(" " if quote else char)
        return "".join(output)

    def _balanced(self, text: str, left: str, right: str) -> bool:
        depth = 0
        for char in text:
            if char == left:
                depth += 1
            elif char == right:
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    def _balanced_quotes(self, text: str) -> bool:
        quote: str | None = None
        escaped = False
        for char in text:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char not in {"'", '"'}:
                continue
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        return quote is None
