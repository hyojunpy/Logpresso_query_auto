from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codeql_workflow_is_disabled_without_private_code_scanning() -> None:
    assert not (ROOT / ".github" / "workflows" / "codeql.yml").exists()


def test_dependabot_updates_python_and_github_actions_dependencies() -> None:
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "version: 2" in config
    assert "package-ecosystem: pip" in config
    assert "package-ecosystem: github-actions" in config
    assert config.count("interval: weekly") == 2


def test_deployment_configuration_has_healthchecks_and_tag_releases() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "HEALTHCHECK" in dockerfile
    assert "/api/v1/health" in dockerfile
    assert compose.count("healthcheck:") == 2
    assert "/_stcore/health" in compose
    assert 'tags:' in release
    assert '"v*"' in release
    assert "DOCS_INTERNAL_DISTRIBUTION_APPROVED" in release
    assert "python -m pytest" in release
    assert "gh release create" in release
    assert "contents: write" in release


def test_ui_user_script_builds_a_standard_pbkdf2_hash() -> None:
    script = (ROOT / "scripts" / "new_ui_user.ps1").read_text(encoding="utf-8")

    assert "'pbkdf2_sha256$' + $iterations + '$'" in script
    assert '"pbkdf2_sha256`$$iterations' not in script


def test_runtime_schema_builder_is_included_in_installed_package() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["app*", "scripts*"]' in pyproject
    assert (ROOT / "scripts" / "__init__.py").exists()


def test_start_scripts_sync_lan_binding_and_clean_stale_https_container() -> None:
    start_dev = (ROOT / "scripts" / "start_dev.ps1").read_text(encoding="utf-8")
    start_https = (ROOT / "scripts" / "start_https.ps1").read_text(encoding="utf-8")
    configure_lan = (ROOT / "scripts" / "configure_lan.ps1").read_text(encoding="utf-8")

    assert "sync_lan_bind.ps1" in start_dev
    assert "sync_lan_bind.ps1" in start_https
    assert 'rm -f "${env:COMPOSE_PROJECT_NAME}-caddy-1"' in start_dev
    assert "-RemoteAddress LocalSubnet" in configure_lan
    assert "-LocalPort 8501,9443" in configure_lan
