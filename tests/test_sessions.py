"""Bounded in-memory session-store tests."""

import pytest

from localface_studio.application.sessions import SessionStore


def test_session_credentials_are_distinct_and_authenticate_together() -> None:
    store = SessionStore()
    record = store.create()

    assert len({record.session_id, record.actor_id, record.csrf_token}) == 3
    assert store.get(record.session_id) == record
    assert store.authenticate(record.session_id, record.csrf_token) == record
    assert store.authenticate(record.session_id, "wrong-token") is None
    assert store.authenticate(None, record.csrf_token) is None


def test_session_store_evicts_least_recently_used_record() -> None:
    store = SessionStore(maximum_sessions=2)
    first = store.create()
    second = store.create()
    assert store.get(first.session_id) == first

    third = store.create()

    assert store.get(first.session_id) == first
    assert store.get(second.session_id) is None
    assert store.get(third.session_id) == third


def test_session_store_requires_positive_bound() -> None:
    with pytest.raises(ValueError, match="positive"):
        SessionStore(maximum_sessions=0)
