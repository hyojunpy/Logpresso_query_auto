"""Offline deployment preflight for Logpresso Query Assistant."""
from __future__ import annotations

import json
import subprocess
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
    _check_llm_limits(config, errors, checks)
    public_origins = [origin for origin in config.cors_allowed_origins if not origin.startswith("http://localhost") and not origin.startswith("http://127.0.0.1")]
    checks["cors_allowed_origins"] = list(config.cors_allowed_origins)
    if public_origins and not config.management_api_key:
        errors.append("management_api_key_required_for_nonlocal_cors")
    checks["management_api_key_configured"] = bool(config.management_api_key)
    tracked_sensitive = _tracked_sensitive_files(getattr(config, "repository_root", ROOT))
    checks["tracked_sensitive_artifacts"] = tracked_sensitive
    if tracked_sensitive:
        errors.append("sensitive_artifact_tracked")
    return {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings, "checks": checks}


def _tracked_sensitive_files(root: str | Path) -> list[str]:
    """Return tracked runtime/secret file names without reading their contents."""
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={Path(root).resolve().as_posix()}", "-C", str(root), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    sensitive: list[str] = []
    for raw_path in result.stdout.splitlines():
        path = raw_path.replace("\\", "/")
        name = Path(path).name.lower()
        if (name.startswith(".env") and name != ".env.example") or Path(name).suffix in {
            ".db", ".sqlite", ".sqlite3", ".log", ".pem", ".key", ".p12", ".pfx"
        }:
            sensitive.append(path)
    return sorted(sensitive)


def _check_llm_limits(config: Any, errors: list[str], checks: dict[str, object]) -> None:
    limits = {
        "ollama_timeout_seconds": (getattr(config, "ollama_timeout_seconds", 45), 1, 300),
        "ollama_num_predict": (getattr(config, "ollama_num_predict", 96), 16, 2_048),
        "ollama_num_ctx": (getattr(config, "ollama_num_ctx", 4_096), 1_024, 32_768),
        "llm_context_limit": (getattr(config, "llm_context_limit", 4), 1, 32),
        "llm_context_excerpt_chars": (getattr(config, "llm_context_excerpt_chars", 600), 100, 10_000),
    }
    for name, (value, minimum, maximum) in limits.items():
        checks[name] = value
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
            errors.append(f"{name}_out_of_range")


def main() -> int:
    result = run_checks(settings)
    # Keep Windows CI logs portable when the configured document path is non-ASCII.
    print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
