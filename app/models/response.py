from typing import Literal

from pydantic import BaseModel

from app.models.request import QueryIntent


class ValidationIssue(BaseModel):
    code: str
    message: str
    evidence: str | None = None
    severity: Literal["info", "warning", "error"] = "error"
    affected_table: str | None = None
    affected_field: str | None = None
    suggestion: str | None = None
    source: Literal["syntax", "documentation", "catalog", "policy"] = "syntax"


class FieldLineage(BaseModel):
    output_field: str
    input_fields: list[str]
    operation: Literal["source", "rename", "eval"]
    source_table: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    commands: list[str] = []
    functions: list[str] = []
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    requires_admin: bool = False
    compatibility_notes: list[str] = []
    field_lineage: list[FieldLineage] = []


class QueryQualityResult(BaseModel):
    safety_score: int
    performance_score: int
    completeness_score: int
    confidence_score: int
    risk_level: Literal["low", "medium", "high", "critical"]
    diagnostics: list[ValidationIssue] = []
    score_reasons: dict[str, list[str]] = {}


class ExecutionPreview(BaseModel):
    status: Literal["not_requested", "preview_ready", "requires_confirmation", "blocked", "unsupported"]
    is_read_only: bool | None = None
    risk_level: Literal["low", "medium", "high", "critical"]
    recommended_limit: int | None = None
    recommended_timeout_seconds: int | None = None
    requires_user_confirmation: bool = False
    blocked_reasons: list[str] = []
    confirmation_message: str | None = None
    checks_before_execution: list[str] = []


class QueryAnalysisResponse(BaseModel):
    validation: ValidationResult
    schema_validation: ValidationResult
    quality: QueryQualityResult
    execution_preview: ExecutionPreview


class QueryExplanation(BaseModel):
    query_part: str
    reason: str
    command: str | None = None
    request_signal: str | None = None


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
    schema_validation: ValidationResult | None = None
    quality: QueryQualityResult | None = None
    execution_preview: ExecutionPreview | None = None
    explanation: list[QueryExplanation] = []
    references: list[QueryReference] = []
    assumptions: list[str] = []
    debug: dict[str, object] = {}


class FeedbackSaveResponse(BaseModel):
    id: int
    created_at: str
    raw_text_stored: bool


class FeedbackSummaryResponse(BaseModel):
    total: int
    ratings: dict[str, int]
    issue_types: dict[str, int]
    unresolved_outcomes: dict[str, int] = {}


class ImprovementCandidate(BaseModel):
    issue_type: str
    count: int
    title: str
    suggestion: str


class ImprovementCandidatesResponse(BaseModel):
    items: list[ImprovementCandidate]


class ImprovementReportResponse(BaseModel):
    total_feedback: int
    ratings: dict[str, int]
    issue_types: dict[str, int]
    candidates: list[ImprovementCandidate]
    priority_issue_types: list[str]
    unresolved_outcomes: dict[str, int] = {}
