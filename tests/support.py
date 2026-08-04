from pathlib import Path
from threading import Lock

from app.services.indexer import DocumentIndex


_INDEX_LOCK = Lock()
_INDEX_READY = False
_INDEX_PATH = Path(".pytest_cache") / "logpresso_test_index.db"
_DOC_PATH = Path("docs") / "로그프레소 쿼리.docx"


def shared_index() -> DocumentIndex:
    global _INDEX_READY
    with _INDEX_LOCK:
        index = DocumentIndex(_INDEX_PATH)
        status = index.status(_DOC_PATH)
        if not _INDEX_READY and (not status["indexed"] or status["stale"]):
            index.rebuild(_DOC_PATH)
            _INDEX_READY = True
        elif status["indexed"] and not status["stale"]:
            _INDEX_READY = True
        return index
