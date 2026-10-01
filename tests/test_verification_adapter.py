import json
from io import BytesIO
from unittest.mock import patch

import pytest

from app.services.verification_adapter import HttpDryRunVerificationAdapter, MockVerificationAdapter, NoopVerificationAdapter, VerificationResult


def test_noop_verification_never_calls_external_system():
    result = NoopVerificationAdapter().verify_dry_run("table firewall_logs")

    assert result.status == "not_configured"
    assert result.external_call_made is False


def test_mock_verification_uses_fixture_outcome_without_io():
    adapter = MockVerificationAdapter({"bad": VerificationResult(status="rejected", message="fixture rejection", diagnostics=["unknown command"])})

    assert adapter.verify_dry_run("bad").status == "rejected"
    assert adapter.verify_dry_run("table firewall_logs").status == "accepted"
    assert adapter.calls == ["bad", "table firewall_logs"]


def test_http_dry_run_adapter_requires_https_or_localhost():
    with pytest.raises(ValueError):
        HttpDryRunVerificationAdapter("http://logpresso.internal/validate")


def test_http_dry_run_adapter_sends_validation_only_payload():
    response = BytesIO(json.dumps({"status": "valid", "message": "ok", "diagnostics": []}).encode())
    with patch("app.services.verification_adapter.urlopen", return_value=response) as mocked:
        result = HttpDryRunVerificationAdapter("https://logpresso.internal/dry-run", "token").verify_dry_run(
            "table firewall_logs"
        )

    request = mocked.call_args.args[0]
    assert json.loads(request.data) == {"query": "table firewall_logs", "dry_run": True}
    assert result.status == "accepted"
    assert result.external_call_made is True
