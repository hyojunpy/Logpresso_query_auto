from pathlib import Path
from types import SimpleNamespace

from docx import Document

from app.services.indexer import DocumentIndex
from scripts.check_deployment import run_checks


def test_preflight_reports_ready_local_configuration_without_external_call(tmp_path: Path):
    doc_path = tmp_path / "manual.docx"
    document = Document()
    document.add_paragraph("table sample_logs")
    document.save(doc_path)
    db_path = tmp_path / "app.db"
    DocumentIndex(db_path).rebuild(doc_path)
    config = SimpleNamespace(
        doc_path=doc_path, db_path=db_path, catalog_path=tmp_path / "catalog.json",
        llm_provider="mock", openai_api_key=None, cors_allowed_origins=("http://localhost:8501",), management_api_key=None,
    )

    result = run_checks(config)

    assert result["status"] == "passed"
    assert result["checks"]["external_call_made"] is False


def test_preflight_rejects_openai_without_key_and_missing_document(tmp_path: Path):
    config = SimpleNamespace(
        doc_path=tmp_path / "missing.docx", db_path=tmp_path / "app.db", catalog_path=tmp_path / "catalog.json",
        llm_provider="openai", openai_api_key=None, cors_allowed_origins=(), management_api_key=None,
    )

    result = run_checks(config)

    assert result["status"] == "failed"
    assert {"reference_document_missing", "openai_api_key_missing"}.issubset(result["errors"])
