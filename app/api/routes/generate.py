from fastapi import APIRouter, Body, Query
from pathlib import Path

from app.core.config import settings
from app.models.request import GenerateQueryRequest, ValidateQueryRequest, RequestContext
from app.models.response import GenerateQueryResponse, QueryAnalysisResponse, ValidationResult
from app.services.indexer import DocumentIndex
from app.services.query_generator import QueryGenerator
from app.services.query_validator import QueryValidator
from app.services.catalog_service import CatalogService
from app.services.execution_preview import ExecutionPreviewService
from app.services.quality_analyzer import QueryQualityAnalyzer
from app.services.retriever import Retriever
from app.services.feedback_store import FeedbackStore

router = APIRouter()


def _retriever() -> Retriever:
    index = DocumentIndex(settings.db_path)
    default_db_path = settings.data_dir / "app.db"
    if Path(settings.db_path).resolve() == default_db_path.resolve() and Path(settings.doc_path).exists():
        index.ensure_current(settings.doc_path)
    return Retriever(index)


GENERATE_EXAMPLES = {
    "generated": {
        "summary": "성공",
        "value": {
            "request": "최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘",
            "context": {
                "product": "ENT",
                "known_tables": ["firewall_logs"],
                "known_fields": ["src_ip", "action", "_time"],
            },
        },
    },
    "needs_clarification": {
        "summary": "확인 질문 필요",
        "value": {
            "request": "에러 로그 보여줘",
            "context": {},
        },
    },
}


VALIDATE_EXAMPLES = {
    "valid": {
        "summary": "검증 성공",
        "value": {"query": "table duration=24h firewall_logs\n| stats count by src_ip"},
    },
    "invalid": {
        "summary": "검증 실패",
        "value": {"query": "unknown firewall_logs"},
    },
    "quoted_text": {
        "summary": "문자열 내부 문법 무시",
        "value": {"query": 'table firewall_logs\n| search message == "duration=24h fake_func(value)"'},
    },
}


@router.post("/query/generate", response_model=GenerateQueryResponse)
def generate_query(payload: GenerateQueryRequest = Body(..., openapi_examples=GENERATE_EXAMPLES)):
    response = QueryGenerator(_retriever()).generate(payload)
    FeedbackStore(settings.db_path).record_generation_outcome(payload.request, response.status)
    return response


@router.post("/query/validate", response_model=ValidationResult)
def validate_query(payload: ValidateQueryRequest = Body(..., openapi_examples=VALIDATE_EXAMPLES)):
    syntax = QueryValidator(_retriever()).validate(payload.query)
    context = payload.context.model_copy(update={"catalog": payload.catalog or payload.context.catalog})
    schema = CatalogService(settings.catalog_path).validate_query(payload.query, context)
    syntax.errors.extend(schema.errors)
    syntax.warnings.extend(schema.warnings)
    syntax.valid = not syntax.errors
    return syntax


@router.post("/query/analyze", response_model=QueryAnalysisResponse)
def analyze_query(payload: ValidateQueryRequest):
    syntax = QueryValidator(_retriever()).validate(payload.query)
    context = payload.context.model_copy(update={"catalog": payload.catalog or payload.context.catalog})
    schema = CatalogService(settings.catalog_path).validate_query(payload.query, context)
    combined = syntax.model_copy(deep=True)
    combined.errors.extend(schema.errors)
    combined.warnings.extend(schema.warnings)
    combined.compatibility_notes.extend(schema.compatibility_notes)
    combined.valid = not combined.errors
    quality = QueryQualityAnalyzer().analyze(payload.query, combined)
    preview = ExecutionPreviewService().build(payload.query if combined.valid else None, combined, quality)
    return QueryAnalysisResponse(validation=combined, schema_validation=schema, quality=quality, execution_preview=preview)


@router.get("/commands/search")
def search_commands(q: str = Query(..., min_length=1, max_length=500)):
    return _retriever().search(q, limit=10)


@router.get("/commands/{command_name}")
def get_command(command_name: str):
    return _retriever().get_entry(command_name)
