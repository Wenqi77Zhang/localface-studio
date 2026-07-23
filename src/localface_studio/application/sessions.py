"""Process-local browser sessions with bounded memory usage."""

from collections import OrderedDict
from dataclasses import dataclass
from hmac import compare_digest
from secrets import token_urlsafe
from threading import RLock


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Opaque credentials kept only in backend memory."""

    session_id: str
    actor_id: str
    csrf_token: str


class SessionStore:
    """Thread-safe least-recently-used session store invalidated on restart."""

    def __init__(self, *, maximum_sessions: int = 128) -> None:
        if maximum_sessions < 1:
            raise ValueError("maximum_sessions must be positive")
        self._maximum_sessions = maximum_sessions
        self._sessions: OrderedDict[str, SessionRecord] = OrderedDict()
        self._lock = RLock()

    def create(self) -> SessionRecord:
        """Create unpredictable session, actor, and CSRF identifiers."""
        with self._lock:
            session_id = self._unique_session_id()
            record = SessionRecord(
                session_id=session_id,
                actor_id=token_urlsafe(24),
                csrf_token=token_urlsafe(32),
            )
            self._sessions[session_id] = record
            while len(self._sessions) > self._maximum_sessions:
                self._sessions.popitem(last=False)
            return record

    def get(self, session_id: str | None) -> SessionRecord | None:
        """Return and refresh an existing session without exposing lookup errors."""
        if session_id is None:
            return None
        with self._lock:
            record = self._sessions.get(session_id)
            if record is not None:
                self._sessions.move_to_end(session_id)
            return record

    def authenticate(
        self,
        session_id: str | None,
        csrf_token: str | None,
    ) -> SessionRecord | None:
        """Validate both credentials using a timing-safe token comparison."""
        record = self.get(session_id)
        if record is None or csrf_token is None:
            return None
        if not compare_digest(record.csrf_token, csrf_token):
            return None
        return record

    def _unique_session_id(self) -> str:
        while True:
            candidate = token_urlsafe(32)
            if candidate not in self._sessions:
                return candidate
