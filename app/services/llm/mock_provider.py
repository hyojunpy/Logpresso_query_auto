from typing import Any
import re

from app.models.document import SearchResult
from app.models.response import ValidationIssue
from app.services.llm.base import LLMProvider
from app.services.llm.json_utils import parse_json_object


class MockProvider(LLMProvider):
    def __init__(
        self,
        generation_response: dict[str, Any] | str | None = None,
        repair_response: dict[str, Any] | str | None = None,
    ):
        self.generation_response = generation_response
        self.repair_response = repair_response

    def generate_json(self, prompt: str, context: list[SearchResult]) -> dict[str, Any]:
        if self.generation_response is not None:
            return parse_json_object(self.generation_response)
        return {"status": "mock", "prompt_length": len(prompt), "context_count": len(context)}

    def repair(self, query: str, errors: list[ValidationIssue], context: list[SearchResult]) -> str:
        if self.repair_response is None:
            return query
        data = parse_json_object(self.repair_response)
        return data.get("query") or query

    def repair_json(self, prompt: str, query: str, errors: list[ValidationIssue], context: list[SearchResult]) -> dict[str, Any]:
        if self.repair_response is not None:
            return parse_json_object(self.repair_response)
        if any(error.code == "unknown_command" for error in errors):
            repaired = re.sub(r"^\s*unknown\s*\|", "", query, flags=re.IGNORECASE)
            if repaired != query:
                return {"status": "generated", "query": repaired.strip()}
        return {"status": "unchanged"}
