"""Offline deployment preflight for Logpresso Query Assistant."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.catalog_service import CatalogService
from app.services.indexer import DocumentIndex


def run_checks(config: Any) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, object] = {"external_call_made": False}
    checks["reference_document"] = str(config.doc_path)
    if not config.doc_path.exists():
        errors.append("reference_document_missing")
    try:
        index = DocumentIndex(config.db_path).status(config.doc_path)
        checks["document_index"] = index
        if not index["indexed"] or index["stale"]:
            warnings.append("document_index_not_ready")
    except Exception:
        errors.append("document_index_unavailable")
    try:
        catalog = CatalogService(config.catalog_path).load()
        checks["catalog_table_count"] = len(catalog.tables) if catalog else 0
    except Exception:
        errors.append("catalog_invalid")
    checks["llm_provider"] = config.llm_provider
    if config.llm_provider not in {"mock", "ollama", "openai"}:
        errors.append("llm_provider_invalid")
    elif config.llm_provider == "openai" and not config.openai_api_key:
        errors.append("openai_api_key_missing")
    elif config.llm_provider == "ollama":
        warnings.append("ollama_connectivity_not_checked")
    public_origins = [origin for origin in config.cors_allowed_origins if not origin.startswith("http://localhost") and not origin.startswith("http://127.0.0.1")]
    checks["cors_allowed_origins"] = list(config.cors_allowed_origins)
    if public_origins and not config.management_api_key:
        warnings.append("management_api_key_not_configured_for_nonlocal_cors")
    checks["management_api_key_configured"] = bool(config.management_api_key)
    return {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings, "checks": checks}


def main() -> int:
    result = run_checks(settings)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
