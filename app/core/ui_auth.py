from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import sqlite3
from pathlib import Path


PBKDF2_ITERATIONS = 200_000


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    username: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class UserAccount:
    password_hash: str
    role: str = "viewer"
    enabled: bool = True


@dataclass(frozen=True)
class AuthEvent:
    timestamp: str
    action: str
    username: str
    actor: str


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


def load_users(raw_json: str) -> dict[str, UserAccount]:
    try:
        value = json.loads(raw_json or "{}")
    except json.JSONDecodeError as error:
        raise ValueError("UI_USERS_JSON must be a JSON object") from error
    if not isinstance(value, dict):
        raise ValueError("UI_USERS_JSON must be a JSON object")
    users: dict[str, UserAccount] = {}
    for raw_name, raw_account in value.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("UI usernames must be non-empty strings")
        if isinstance(raw_account, str):
            account = UserAccount(password_hash=raw_account, role="admin")
        elif isinstance(raw_account, dict):
            password_hash = raw_account.get("password_hash")
            role = raw_account.get("role", "viewer")
            if not isinstance(password_hash, str) or role not in {"viewer", "editor", "admin"}:
                raise ValueError("UI user entries require password_hash and viewer/editor/admin role")
            account = UserAccount(password_hash=password_hash, role=role)
        else:
            raise ValueError("UI user entries must be strings or objects")
        users[raw_name.strip()] = account
    return users


def authenticate(username: str, password: str, users: dict[str, UserAccount]) -> AuthResult:
    normalized = username.strip()
    account = users.get(normalized)
    stored = account.password_hash if account else "pbkdf2_sha256$200000$AA==$AA=="
    ok = account is not None and verify_password(password, stored)
    return AuthResult(ok=ok, username=normalized if ok else None, role=account.role if ok and account else None)


class LoginAttemptStore:
    def __init__(self, path: Path, max_failures: int = 5, lockout_minutes: int = 15):
        self.path = path
        self.max_failures = max_failures
        self.lockout_minutes = lockout_minutes

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute(
            "create table if not exists login_attempt (username text primary key, failures integer not null, locked_until text)"
        )
        conn.execute(
            "create table if not exists ui_user (username text primary key, password_hash text not null, "
            "role text not null, enabled integer not null default 1, created_at text not null, updated_at text not null)"
        )
        conn.execute(
            "create table if not exists auth_event (id integer primary key autoincrement, timestamp text not null, "
            "action text not null, username text not null, actor text not null)"
        )
        return conn

    def seed_users(self, users: dict[str, UserAccount]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                "insert or ignore into ui_user(username,password_hash,role,enabled,created_at,updated_at) "
                "values (?, ?, ?, ?, ?, ?)",
                [(name, account.password_hash, account.role, int(account.enabled), now, now) for name, account in users.items()],
            )

    def users(self, *, include_disabled: bool = False) -> dict[str, UserAccount]:
        where = "" if include_disabled else " where enabled = 1"
        with self._connect() as conn:
            rows = conn.execute("select username,password_hash,role,enabled from ui_user" + where + " order by username").fetchall()
        return {row[0]: UserAccount(password_hash=row[1], role=row[2], enabled=bool(row[3])) for row in rows}

    def save_user(self, username: str, password_hash: str, role: str, *, actor: str) -> None:
        normalized = username.strip()
        if not normalized or role not in {"viewer", "editor", "admin"} or not password_hash:
            raise ValueError("username, password_hash and a valid role are required")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "insert into ui_user(username,password_hash,role,enabled,created_at,updated_at) values (?, ?, ?, 1, ?, ?) "
                "on conflict(username) do update set password_hash=excluded.password_hash, role=excluded.role, "
                "enabled=1, updated_at=excluded.updated_at",
                (normalized, password_hash, role, now, now),
            )
        self.record_event("user_saved", normalized, actor)

    def set_password(self, username: str, password_hash: str, *, actor: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            result = conn.execute(
                "update ui_user set password_hash = ?, updated_at = ? where username = ?",
                (password_hash, now, username.strip()),
            )
            if result.rowcount != 1:
                raise ValueError("user not found")
        self.record_event("password_changed", username.strip(), actor)

    def unlock(self, username: str, *, actor: str) -> None:
        self.clear(username)
        self.record_event("account_unlocked", username.strip(), actor)

    def record_event(self, action: str, username: str, actor: str = "system") -> None:
        with self._connect() as conn:
            conn.execute(
                "insert into auth_event(timestamp,action,username,actor) values (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), action, username.strip() or "<empty>", actor),
            )

    def recent_events(self, limit: int = 100) -> list[AuthEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "select timestamp,action,username,actor from auth_event order by id desc limit ?", (max(1, limit),)
            ).fetchall()
        return [AuthEvent(*row) for row in rows]

    def locked_seconds(self, username: str, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute("select locked_until from login_attempt where username = ?", (username.strip(),)).fetchone()
        if not row or not row[0]:
            return 0
        locked_until = datetime.fromisoformat(row[0])
        return max(0, int((locked_until - current).total_seconds()))

    def record_failure(self, username: str, *, now: datetime | None = None) -> int:
        normalized = username.strip() or "<empty>"
        current = now or datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute("select failures from login_attempt where username = ?", (normalized,)).fetchone()
            failures = (row[0] if row else 0) + 1
            locked_until = None
            if failures >= self.max_failures:
                locked_until = (current + timedelta(minutes=self.lockout_minutes)).isoformat()
                failures = 0
            conn.execute(
                "insert into login_attempt(username, failures, locked_until) values (?, ?, ?) "
                "on conflict(username) do update set failures=excluded.failures, locked_until=excluded.locked_until",
                (normalized, failures, locked_until),
            )
        return self.locked_seconds(normalized, now=current)

    def clear(self, username: str) -> None:
        with self._connect() as conn:
            conn.execute("delete from login_attempt where username = ?", (username.strip(),))


def session_expired(last_seen: datetime | None, idle_minutes: int, *, now: datetime | None = None) -> bool:
    if last_seen is None:
        return True
    current = now or datetime.now(timezone.utc)
    return current - last_seen > timedelta(minutes=idle_minutes)
