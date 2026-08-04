from fastapi import APIRouter, Body, Query
from pathlib import Path

from app.core.config import settings
from app.models.request import GenerateQueryRequest, ValidateQueryRequest
from app.models.response import GenerateQueryResponse, ValidationResult
from app.services.indexer import DocumentIndex
from app.services.query_generator import QueryGenerator
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever

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
    return QueryGenerator(_retriever()).generate(payload)


@router.post("/query/validate", response_model=ValidationResult)
def validate_query(payload: ValidateQueryRequest = Body(..., openapi_examples=VALIDATE_EXAMPLES)):
    return QueryValidator(_retriever()).validate(payload.query)


@router.get("/commands/search")
def search_commands(q: str = Query(..., min_length=1)):
    return _retriever().search(q, limit=10)


@router.get("/commands/{command_name}")
def get_command(command_name: str):
    return _retriever().get_entry(command_name)
