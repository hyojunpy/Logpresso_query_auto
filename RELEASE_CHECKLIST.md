# Release checklist

Complete every item before creating a `v*` tag.

## Rights and repository settings

- [x] Record repository-owner approval to share `docs/로그프레소 쿼리.docx` with internal collaborators of the private repository.
- [ ] Confirm public publication, external redistribution, or modification rights before any broader distribution of the DOCX.
- [x] Keep the repository without an open-source license; all code rights remain reserved.
- [x] Set the GitHub repository variable `DOCS_INTERNAL_DISTRIBUTION_APPROVED` to `true` after this internal-sharing approval is recorded.
- [ ] Confirm that no `.env`, API key, credential, generated database, or private log is tracked.

## Version and verification

- [ ] Update `project.version` in `pyproject.toml` to match the intended tag.
- [ ] Confirm the release notes include the intended version and date.
- [ ] Run `python -m pytest`.
- [ ] Run `docker compose config --quiet`.
- [ ] In PowerShell, set `$env:COMPOSE_PROJECT_NAME = 'logpresso-release-check'` and `$env:LOGPRESSO_DATA_DIR = '.docker-release-check'`, then run `docker compose up --build --detach` and confirm both service health checks.
- [ ] Stop the release-check stack with the same `COMPOSE_PROJECT_NAME` and `LOGPRESSO_DATA_DIR` values, then remove only `.docker-release-check`.
- [ ] Confirm the `main` branch CI passes. CodeQL is disabled while this private repository does not have Code Scanning available.
- [ ] For Ollama-enabled release environments, run the one-case Gold Set smoke evaluation and review aggregate fallback/timeout counters.

## Publish

```powershell
git tag v0.1.1
git push origin v0.1.1
```

The tag workflow reruns the test suite before creating the GitHub Release.
