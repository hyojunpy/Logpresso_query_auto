"""Dry-run-only boundary for future non-production query verification.

No adapter in this module opens a customer connection. A deployment-specific
adapter must be explicitly provided after security review.
"""
from __future__ import annotations

import json
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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


class HttpDryRunVerificationAdapter:
    """Explicit opt-in adapter for a customer-approved validation-only endpoint."""

    def __init__(self, url: str, token: str | None = None, timeout_seconds: float = 10):
        parsed = urlparse(url)
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("검증 URL은 HTTPS 또는 로컬호스트만 사용할 수 있습니다.")
        self.url = url
        self.token = token
        self.timeout_seconds = max(1.0, min(timeout_seconds, 30.0))

    def verify_dry_run(self, query: str) -> VerificationResult:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            self.url,
            data=json.dumps({"query": query, "dry_run": True}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            return VerificationResult(
                status="rejected", message="외부 dry-run 검증 요청에 실패했습니다.",
                diagnostics=[type(error).__name__], external_call_made=True, adapter="http_dry_run",
            )
        accepted = bool(payload.get("accepted")) or str(payload.get("status", "")).lower() in {"accepted", "ok", "valid"}
        diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
        return VerificationResult(
            status="accepted" if accepted else "rejected",
            message=str(payload.get("message") or ("Dry-run accepted." if accepted else "Dry-run rejected.")),
            diagnostics=[str(item) for item in diagnostics[:20]], external_call_made=True, adapter="http_dry_run",
        )
