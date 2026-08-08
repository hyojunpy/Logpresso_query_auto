"""Integration boundary for customer-managed authentication.

The application intentionally does not own passwords or tokens. A reverse
proxy or existing identity provider can forward an actor identifier through
`X-Actor-ID`; routes only use it for audit attribution until real access
control is wired in at deployment time.
"""

from __future__ import annotations

from hmac import compare_digest

from fastapi import HTTPException, Request, status

from app.core.config import settings


def audit_actor(request: Request) -> str | None:
    actor = request.headers.get("X-Actor-ID", "").strip()
    return actor[:120] or None


def require_management_access(request: Request) -> None:
    """Protect management routes only when a deployment key is configured."""
    expected_key = settings.management_api_key
    if not expected_key:
        return
    supplied_key = request.headers.get("X-Management-API-Key", "")
    if not compare_digest(supplied_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="management API key is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
