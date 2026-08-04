from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codeql_workflow_keeps_python_security_analysis_enabled() -> None:
    workflow = (ROOT / ".github" / "workflows" / "codeql.yml").read_text(
        encoding="utf-8"
    )

    assert "github/codeql-action/init@v4" in workflow
    assert "github/codeql-action/analyze@v4" in workflow
    assert "languages: python" in workflow
    assert "security-events: write" in workflow
    assert "schedule:" in workflow


def test_dependabot_updates_python_and_github_actions_dependencies() -> None:
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "version: 2" in config
    assert "package-ecosystem: pip" in config
    assert "package-ecosystem: github-actions" in config
    assert config.count("interval: weekly") == 2
