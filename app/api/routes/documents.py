from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.indexer import DocumentIndex

router = APIRouter()


@router.post("/reindex")
def reindex() -> dict[str, object]:
    if not Path(settings.doc_path).exists():
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "code": "document_not_found",
                "message": f"문서를 찾을 수 없습니다: {settings.doc_path}",
            },
        )
    index = DocumentIndex(settings.db_path)
    result = index.rebuild(settings.doc_path)
    return {"status": "indexed", **result}


@router.get("/status")
def status() -> dict[str, object]:
    index = DocumentIndex(settings.db_path)
    return index.status(settings.doc_path)
