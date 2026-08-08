"""Dry-run-only boundary for future non-production query verification.

No adapter in this module opens a customer connection. A deployment-specific
adapter must be explicitly provided after security review.
"""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel


class VerificationResult(BaseModel):
    status: Literal["not_configured", "accepted", "rejected"]
    message: str
    diagnostics: list[str] = []
    external_call_made: bool = False
    adapter: str = "noop"


class QueryVerificationAdapter(Protocol):
    def verify_dry_run(self, query: str) -> VerificationResult: ...


class NoopVerificationAdapter:
    def verify_dry_run(self, query: str) -> VerificationResult:
        return VerificationResult(
            status="not_configured",
            message="External verification is not configured. No customer system was contacted.",
            diagnostics=["Configure a customer-approved non-production adapter before verification."],
            adapter="noop",
        )


class MockVerificationAdapter:
    """Fixture-only adapter for contract tests; it never performs I/O."""

    def __init__(self, outcomes: dict[str, VerificationResult] | None = None):
        self.outcomes = outcomes or {}
        self.calls: list[str] = []

    def verify_dry_run(self, query: str) -> VerificationResult:
        self.calls.append(query)
        return self.outcomes.get(query, VerificationResult(status="accepted", message="Mock dry-run accepted.", adapter="mock"))
