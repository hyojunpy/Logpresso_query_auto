"""Integration boundary for customer-managed authentication.

The application intentionally does not own passwords or tokens. A reverse
proxy or existing identity provider can forward an actor identifier through
`X-Actor-ID`; routes only use it for audit attribution until real access
control is wired in at deployment time.
"""

from fastapi import Request


def audit_actor(request: Request) -> str | None:
    actor = request.headers.get("X-Actor-ID", "").strip()
    return actor[:120] or None
