# Release Notes

## 0.1.4 - 2026-08-18

- Added 63 categorized quick-test requests with automatic sample table, stream, logger, and field hints.
- Made all 63 quick tests generate validated queries without clarification prompts and added exhaustive regression coverage.
- Improved login-failure, full-text boolean, multi-field grouping, aggregate threshold, structured parser, stream forwarding, and implicit join-key parsing.
- Added quick-test search, generation readiness indicators, readable documentation references, and table-specific fixture catalogs in the UI.
- Fixed schema validation for computed fields and live stream/logger sources.
- Added live source mounts and an offline-friendly PowerShell startup command for Docker development.
- Restored the local Python 3.12 development environment and expanded query/UI regression tests.

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
# v0.1.9

- 웹에서 사용자 계정을 생성하거나 권한과 비밀번호를 변경할 수 있습니다.
- 모든 사용자가 자신의 비밀번호를 변경할 수 있고, 관리자는 잠긴 계정을 즉시 해제할 수 있습니다.
- 사용자 변경 사항을 재시작 후에도 유지하며 환경 변수 계정은 최초 실행 시 안전하게 이관합니다.
- 로그인 성공·실패·잠금·로그아웃과 계정 변경 감사 로그를 원문 비밀번호 없이 기록합니다.

# v0.1.8

- Added automatic active-LAN IPv4 detection before HTTP and HTTPS startup.
- Changed the Windows firewall boundary to `LocalSubnet` on ports 8501 and
  9443 so DHCP address changes do not require rule replacement.
- Removed stale Caddy containers when returning to HTTP-only development mode.

# v0.1.7

- Fixed PowerShell PBKDF2 hash serialization so passwords created by
  `new_ui_user.ps1` authenticate correctly.
- Added a regression check for the password-hash construction syntax.

# v0.1.6

- Fixed the Caddy healthcheck to use the configured LAN certificate address and
  moved the HTTPS endpoint to port 9443 to avoid stale Windows port reservations.

# v0.1.5

- Added PBKDF2-protected LAN UI login, idle expiration, five-attempt lockout,
  and viewer/editor/admin roles.
- Added concurrent health and real query-generation load tests.
- Added persistent privacy-safe JSON logs, API/Ollama monitoring, optional
  webhook alerts, scheduled daily backups, retention cleanup, and restore
  integrity rehearsal.
- Added LAN setup, Windows auto-start/maintenance tasks, and a Caddy-based
  internal HTTPS endpoint with documented CA distribution.
- Kept the API bound to loopback while allowing the UI on an explicitly chosen
  LAN address.
