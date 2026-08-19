from datetime import datetime, timedelta, timezone

import pytest

from app.core.ui_auth import authenticate, hash_password, load_users, session_expired, verify_password


def test_password_hash_and_authentication():
    encoded = hash_password("correct horse", salt=b"0123456789abcdef", iterations=1_000)
    assert verify_password("correct horse", encoded)
    assert not verify_password("wrong", encoded)
    assert authenticate("alice", "correct horse", {"alice": encoded}).username == "alice"
    assert not authenticate("unknown", "correct horse", {"alice": encoded}).ok


def test_load_users_rejects_invalid_shape():
    assert load_users('{"alice":"hash"}') == {"alice": "hash"}
    with pytest.raises(ValueError):
        load_users("[]")


def test_idle_expiration():
    now = datetime.now(timezone.utc)
    assert not session_expired(now - timedelta(minutes=4), 5, now=now)
    assert session_expired(now - timedelta(minutes=6), 5, now=now)
