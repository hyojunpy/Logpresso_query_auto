from datetime import datetime, timedelta, timezone

import pytest

from app.core.ui_auth import LoginAttemptStore, authenticate, hash_password, load_users, session_expired, verify_password


def test_password_hash_and_authentication():
    encoded = hash_password("correct horse", salt=b"0123456789abcdef", iterations=1_000)
    assert verify_password("correct horse", encoded)
    assert not verify_password("wrong", encoded)
    users = load_users('{"alice":{"password_hash":"' + encoded + '","role":"editor"}}')
    result = authenticate("alice", "correct horse", users)
    assert result.username == "alice"
    assert result.role == "editor"
    assert not authenticate("unknown", "correct horse", users).ok


def test_load_users_rejects_invalid_shape():
    assert load_users('{"alice":"hash"}')["alice"].role == "admin"
    with pytest.raises(ValueError):
        load_users("[]")


def test_idle_expiration():
    now = datetime.now(timezone.utc)
    assert not session_expired(now - timedelta(minutes=4), 5, now=now)
    assert session_expired(now - timedelta(minutes=6), 5, now=now)


def test_login_attempt_lockout_and_clear(tmp_path):
    store = LoginAttemptStore(tmp_path / "auth.db", max_failures=3, lockout_minutes=15)
    now = datetime.now(timezone.utc)
    assert store.record_failure("alice", now=now) == 0
    assert store.record_failure("alice", now=now) == 0
    assert store.record_failure("alice", now=now) > 0
    assert store.locked_seconds("alice", now=now) > 0
    store.clear("alice")
    assert store.locked_seconds("alice", now=now) == 0


def test_persistent_users_password_unlock_and_audit(tmp_path):
    store = LoginAttemptStore(tmp_path / "auth.db", max_failures=1)
    original = hash_password("old", iterations=1_000)
    store.seed_users({"admin": load_users('{"admin":"' + original + '"}')["admin"]})
    # Environment seeding must not overwrite changes made in the UI.
    changed = hash_password("new", iterations=1_000)
    store.set_password("admin", changed, actor="admin")
    store.seed_users({"admin": load_users('{"admin":"' + original + '"}')["admin"]})
    assert verify_password("new", store.users()["admin"].password_hash)

    store.save_user("analyst", hash_password("pw", iterations=1_000), "viewer", actor="admin")
    assert store.users()["analyst"].role == "viewer"
    store.record_failure("analyst")
    assert store.locked_seconds("analyst") > 0
    store.unlock("analyst", actor="admin")
    assert store.locked_seconds("analyst") == 0
    assert [event.action for event in store.recent_events()] == ["account_unlocked", "user_saved", "password_changed"]
