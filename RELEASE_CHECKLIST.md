# Release checklist

Complete every item before creating a `v*` tag.

## Rights and repository settings

- [ ] Confirm in writing that `docs/로그프레소 쿼리.docx` may be redistributed in this repository.
- [ ] Select and add a software license with the code owner's approval.
- [ ] Set the GitHub repository variable `DOCS_PUBLICATION_APPROVED` to `true` only after the documentation approval is recorded.
- [ ] Confirm that no `.env`, API key, credential, generated database, or private log is tracked.

## Version and verification

- [ ] Update `project.version` in `pyproject.toml` to match the intended tag.
- [ ] Run `python -m pytest`.
- [ ] Run `docker compose config --quiet`.
- [ ] In PowerShell, set `$env:LOGPRESSO_DATA_DIR = '.docker-release-check'`, then run `docker compose up --build --detach` and confirm both service health checks.
- [ ] Stop the release-check stack with the same `LOGPRESSO_DATA_DIR` value and remove only `.docker-release-check`.
- [ ] Confirm the `main` branch CI and CodeQL workflows pass.

## Publish

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The tag workflow reruns the test suite before creating the GitHub Release.
