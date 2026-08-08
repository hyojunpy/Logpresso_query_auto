# Release Notes

## Unreleased

- Added catalog CSV import/export support for node, namespace, table
  description, and nullable metadata.
- Added catalog backups and restore APIs with management audit metadata.
- Added explicit table identifier precedence over broad business aliases.
- Added session-only Ollama comparison history and clearer validation summaries.
- Isolated Compose test data through `LOGPRESSO_DATA_DIR` so CI and local
  integration checks do not modify operational `data/` files.
- Added readiness diagnostics, catalog backup comparisons, alias conflict
  diagnostics/export, hashed non-success generation counters, field lineage
  display, and a dry-run-only verification adapter contract.

## Verification

- `python -m pytest -q`
- `RUN_BROWSER_TESTS=1 python -m pytest tests/test_streamlit_browser.py -q`
- `docker compose config --quiet`
- Start Compose with a disposable data directory and verify API/UI health.
