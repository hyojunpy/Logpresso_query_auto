from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets


PBKDF2_ITERATIONS = 200_000


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    username: str | None = None


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(raw_digest, validate=True)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(raw_salt, validate=True), int(raw_iterations)
        )
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def load_users(raw_json: str) -> dict[str, str]:
    try:
        value = json.loads(raw_json or "{}")
    except json.JSONDecodeError as error:
        raise ValueError("UI_USERS_JSON must be a JSON object") from error
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError("UI_USERS_JSON must map usernames to password hashes")
    return {key.strip(): password_hash for key, password_hash in value.items() if key.strip()}


def authenticate(username: str, password: str, users: dict[str, str]) -> AuthResult:
    normalized = username.strip()
    stored = users.get(normalized, "pbkdf2_sha256$200000$AA==$AA==")
    ok = normalized in users and verify_password(password, stored)
    return AuthResult(ok=ok, username=normalized if ok else None)


def session_expired(last_seen: datetime | None, idle_minutes: int, *, now: datetime | None = None) -> bool:
    if last_seen is None:
        return True
    current = now or datetime.now(timezone.utc)
    return current - last_seen > timedelta(minutes=idle_minutes)
