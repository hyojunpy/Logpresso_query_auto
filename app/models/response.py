from typing import Literal

from pydantic import BaseModel

from app.models.request import QueryIntent


class ValidationIssue(BaseModel):
    code: str
    message: str
    evidence: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    commands: list[str] = []
    functions: list[str] = []
    risk_level: Literal["low", "medium", "high"] = "low"
    requires_admin: bool = False
    compatibility_notes: list[str] = []


class QueryExplanation(BaseModel):
    query_part: str
    reason: str


class QueryReference(BaseModel):
    entry_name: str | None
    section: str | None
    reason: str
    excerpt: str | None = None
    options: list[str] = []
    functions: list[str] = []


class GenerateQueryResponse(BaseModel):
    status: Literal["generated", "needs_clarification", "unsupported"]
    query: str | None = None
    questions: list[str] = []
    intent: QueryIntent | None = None
    validation: ValidationResult | None = None
    explanation: list[QueryExplanation] = []
    references: list[QueryReference] = []
    assumptions: list[str] = []
    debug: dict[str, object] = {}
