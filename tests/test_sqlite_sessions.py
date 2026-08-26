"""Restart persistence and expiry tests for local browser sessions."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from localface_studio.infrastructure.sqlite_sessions import SqliteSessionStore


def test_session_survives_store_restart_without_persisting_cookie(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    first_store = SqliteSessionStore(database)
    first_store.initialize()
    created = first_store.create()

    second_store = SqliteSessionStore(database)
    second_store.initialize()
    recovered = second_store.get(created.session_id)

    assert recovered == created
    assert second_store.authenticate(created.session_id, created.csrf_token) == created
    with second_store._connection() as connection:
        stored = connection.execute("SELECT * FROM browser_sessions").fetchone()
    assert stored is not None
    assert created.session_id not in tuple(str(value) for value in stored)


def test_expired_session_is_removed_and_rejected(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    database = tmp_path / "runtime.sqlite3"
    store = SqliteSessionStore(
        database,
        lifetime=timedelta(minutes=5),
        clock=lambda: now,
    )
    store.initialize()
    created = store.create()

    expired_store = SqliteSessionStore(
        database,
        lifetime=timedelta(minutes=5),
        clock=lambda: now + timedelta(minutes=6),
    )
    expired_store.initialize()

    assert expired_store.get(created.session_id) is None


def test_sqlite_session_store_requires_aware_clock(tmp_path: Path) -> None:
    store = SqliteSessionStore(
        tmp_path / "runtime.sqlite3",
        clock=lambda: datetime.now(),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        store.initialize()


def test_sqlite_session_store_evicts_least_recently_used_record(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    now = datetime.now(UTC)
    ticks = iter(now + timedelta(seconds=second) for second in range(10))
    store = SqliteSessionStore(database, maximum_sessions=2, clock=lambda: next(ticks))
    store.initialize()
    first = store.create()
    second = store.create()
    assert store.get(first.session_id) == first

    third = store.create()

    assert store.get(first.session_id) == first
    assert store.get(second.session_id) is None
    assert store.get(third.session_id) == third
