# Release checklist

Complete every item before creating a `v*` tag.

## Rights and repository settings

- [x] Record repository-owner approval to share `docs/로그프레소 쿼리.docx` with internal collaborators of the private repository.
- [ ] Confirm public publication, external redistribution, or modification rights before any broader distribution of the DOCX.
- [x] Keep the repository without an open-source license; all code rights remain reserved.
- [x] Set the GitHub repository variable `DOCS_INTERNAL_DISTRIBUTION_APPROVED` to `true` after this internal-sharing approval is recorded.
- [x] Confirm that no `.env`, API key, credential, generated database, or private log is tracked.

## Version and verification

- [x] Update `project.version` in `pyproject.toml` to match the intended tag.
- [x] Confirm the release notes include the intended version and date.
- [x] Run `python -m pytest` (246 passed, 1 skipped, 85 deselected).
- [x] Run `docker compose config --quiet` (Docker CLI 29.7.2, Compose v5.3.1).
- [x] In PowerShell, set `$env:COMPOSE_PROJECT_NAME = 'logpresso-release-check'` and `$env:LOGPRESSO_DATA_DIR = '.docker-release-check'`, then run `docker compose up --build --detach` and confirm both service health checks (API/UI healthy; HTTP 200).
- [x] Stop the release-check stack with the same `COMPOSE_PROJECT_NAME` and `LOGPRESSO_DATA_DIR` values, then remove only `.docker-release-check`.
- [ ] Confirm the `main` branch CI passes for the `v0.1.4` release preparation. CodeQL is disabled while this private repository does not have Code Scanning available.
- [x] For Ollama-enabled release environments, run the one-case Gold Set smoke evaluation and review aggregate fallback/timeout counters (semantic and validation passed; 1 safe template fallback, 0 timeouts with `llama3.2:3b`).

## Publish

```powershell
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

The tag workflow reruns the test suite before creating the GitHub Release.
