# Release Notes

## 0.1.3 - 2026-08-17

- Expanded query intent parsing for logger and stream windows, structured parser options, explode fields, explicit source ordering, and offsets.
- Improved full-text range, quoted compound-expression, conjunction, sort, and schema-bounded filter handling.
- Added node-qualified table deduplication and cleaner field-lineage evaluation inputs.
- Reused Ollama sessions with a bounded keep-alive and exposed candidate/fallback diagnostics for debugging.
- Improved query copy, download, and validation feedback in the UI.
- Added a non-blocking advanced-parser roadmap workflow and documented the security gate for file-backed sources.
- Raised the advanced-parser baseline from 56 passing and 38 failing to 76 passing and 16 failing; 13 remaining cases require the file-source security gate.

## 0.1.2 - 2026-08-17

- Isolated the Streamlit browser regression test from Docker-oriented LLM environment values.
- Hardened local-model JSON recovery for fenced responses, embedded objects, and trailing commas.
- Added opt-out automatic document indexing on readiness checks for a smoother first startup.
- Added an offline tracked-file check for environment files, databases, logs, and private-key artifacts.
- Improved schema-bounded error-field inference and recorded the advanced-parser baseline (56 passing, 38 failing).
- Retained file-source work behind its security entry criteria.

## 0.1.1 - 2026-08-11

- Bounded Ollama retrieval context, output budget, and request context window
  to improve local-model responsiveness.
- Added privacy-safe Ollama timing buckets, operational warnings, and a
  bounded development smoke evaluation for context-quality checks.
- Classified malformed Ollama output as a fallback condition and kept timeout
  handling retry-free.
- Made Compose pass the same Ollama and metrics settings as local deployment.
- Require a management key during deployment preflight when non-local CORS is
  configured.

## Previous Unreleased Work

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
