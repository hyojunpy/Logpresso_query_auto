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


def test_preflight_rejects_out_of_range_llm_context_settings(tmp_path: Path):
    config = SimpleNamespace(
        doc_path=tmp_path / "missing.docx", db_path=tmp_path / "app.db", catalog_path=tmp_path / "catalog.json",
        llm_provider="ollama", openai_api_key=None, cors_allowed_origins=(), management_api_key=None,
        ollama_timeout_seconds=0, ollama_num_predict=4, ollama_num_ctx=512, llm_context_limit=0, llm_context_excerpt_chars=99,
    )

    result = run_checks(config)

    assert {"ollama_timeout_seconds_out_of_range", "ollama_num_predict_out_of_range", "ollama_num_ctx_out_of_range", "llm_context_limit_out_of_range", "llm_context_excerpt_chars_out_of_range"}.issubset(result["errors"])


def test_preflight_rejects_nonlocal_cors_without_management_key(tmp_path: Path):
    config = SimpleNamespace(
        doc_path=tmp_path / "missing.docx", db_path=tmp_path / "app.db", catalog_path=tmp_path / "catalog.json",
        llm_provider="mock", openai_api_key=None, cors_allowed_origins=("https://query.example.com",), management_api_key=None,
    )

    result = run_checks(config)

    assert "management_api_key_required_for_nonlocal_cors" in result["errors"]
