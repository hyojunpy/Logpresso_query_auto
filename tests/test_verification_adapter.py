from app.services.verification_adapter import MockVerificationAdapter, NoopVerificationAdapter, VerificationResult


def test_noop_verification_never_calls_external_system():
    result = NoopVerificationAdapter().verify_dry_run("table firewall_logs")

    assert result.status == "not_configured"
    assert result.external_call_made is False


def test_mock_verification_uses_fixture_outcome_without_io():
    adapter = MockVerificationAdapter({"bad": VerificationResult(status="rejected", message="fixture rejection", diagnostics=["unknown command"])})

    assert adapter.verify_dry_run("bad").status == "rejected"
    assert adapter.verify_dry_run("table firewall_logs").status == "accepted"
    assert adapter.calls == ["bad", "table firewall_logs"]
