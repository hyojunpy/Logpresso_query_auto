from abc import ABC, abstractmethod
from typing import Any

from app.models.document import SearchResult
from app.models.response import ValidationIssue


class LLMProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str, context: list[SearchResult]) -> dict[str, Any]:
        raise NotImplementedError

    def repair(self, query: str, errors: list[ValidationIssue], context: list[SearchResult]) -> str:
        return query

    def repair_json(self, prompt: str, query: str, errors: list[ValidationIssue], context: list[SearchResult]) -> dict[str, Any]:
        repaired = self.repair(query, errors, context)
        return {"status": "generated", "query": repaired} if repaired != query else {"status": "unchanged"}
