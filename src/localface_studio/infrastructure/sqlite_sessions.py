"""Restart-safe local browser sessions backed by the task database."""

import hashlib
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from sqlite3 import Connection, Row
from threading import RLock

from localface_studio.application.sessions import SessionRecord, SessionStore

SESSION_LIFETIME = timedelta(hours=24)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SqliteSessionStore(SessionStore):
    """Persist opaque local sessions without storing the browser cookie value."""

    def __init__(
        self,
        database_path: Path,
        *,
        maximum_sessions: int = 128,
        lifetime: timedelta = SESSION_LIFETIME,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        super().__init__(maximum_sessions=maximum_sessions)
        if lifetime <= timedelta(0):
            raise ValueError("session lifetime must be positive")
        self._database_path = database_path
        self._maximum_sessions = maximum_sessions
        self._lifetime = lifetime
        self._clock = clock
        self._database_lock = RLock()

    def initialize(self) -> None:
        """Create the minimal session schema and discard expired credentials."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._database_lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    session_digest TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_browser_sessions_expiry
                    ON browser_sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_browser_sessions_last_seen
                    ON browser_sessions(last_seen_at);
                """
            )
            self._remove_expired(connection, self._now())

    def create(self) -> SessionRecord:
        """Create independent cookie, actor, and CSRF credentials."""
        now = self._now()
        with self._database_lock, self._connection() as connection:
            self._remove_expired(connection, now)
            while True:
                record = SessionRecord(
                    session_id=token_urlsafe(32),
                    actor_id=token_urlsafe(24),
                    csrf_token=token_urlsafe(32),
                )
                try:
                    connection.execute(
                        """
                        INSERT INTO browser_sessions (
                            session_digest, actor_id, csrf_token,
                            created_at, last_seen_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self._digest(record.session_id),
                            record.actor_id,
                            record.csrf_token,
                            now.isoformat(),
                            now.isoformat(),
                            (now + self._lifetime).isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    continue
                self._enforce_bound(connection)
                return record

    def get(self, session_id: str | None) -> SessionRecord | None:
        """Recover and refresh a valid session across backend restarts."""
        if session_id is None:
            return None
        now = self._now()
        with self._database_lock, self._connection() as connection:
            self._remove_expired(connection, now)
            row = connection.execute(
                """
                SELECT actor_id, csrf_token
                FROM browser_sessions
                WHERE session_digest = ?
                """,
                (self._digest(session_id),),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE browser_sessions
                SET last_seen_at = ?, expires_at = ?
                WHERE session_digest = ?
                """,
                (now.isoformat(), (now + self._lifetime).isoformat(), self._digest(session_id)),
            )
            return SessionRecord(
                session_id=session_id,
                actor_id=str(row["actor_id"]),
                csrf_token=str(row["csrf_token"]),
            )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("session clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    @staticmethod
    def _digest(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _remove_expired(connection: Connection, now: datetime) -> None:
        connection.execute(
            "DELETE FROM browser_sessions WHERE expires_at <= ?",
            (now.isoformat(),),
        )

    def _enforce_bound(self, connection: Connection) -> None:
        connection.execute(
            """
            DELETE FROM browser_sessions
            WHERE session_digest IN (
                SELECT session_digest
                FROM browser_sessions
                ORDER BY last_seen_at ASC
                LIMIT MAX((SELECT COUNT(*) FROM browser_sessions) - ?, 0)
            )
            """,
            (self._maximum_sessions,),
        )

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()
