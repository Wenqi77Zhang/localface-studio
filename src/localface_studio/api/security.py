"""Loopback request-source and browser-session protections."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from starlette.responses import JSONResponse, Response

from localface_studio.application.sessions import SessionRecord, SessionStore
from localface_studio.infrastructure.config import Settings

SESSION_COOKIE = "localface_session"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FRONTEND_PORTS = frozenset({4173, 5173})


def reject_untrusted_source(request: Request, settings: Settings) -> Response | None:
    """Reject DNS rebinding, cross-site browser requests, and invalid origins."""
    if request.url.hostname != settings.host:
        return _error(status.HTTP_400_BAD_REQUEST, "invalid request host")

    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site == "cross-site":
        return _error(status.HTTP_403_FORBIDDEN, "cross-site requests are not allowed")

    origin = request.headers.get("origin")
    if origin is not None and not _is_allowed_origin(origin, settings):
        return _error(status.HTTP_403_FORBIDDEN, "request origin is not allowed")
    if request.method in UNSAFE_METHODS and origin is None:
        return _error(status.HTTP_403_FORBIDDEN, "request origin is required")
    return None


def reject_invalid_csrf(request: Request, sessions: SessionStore) -> Response | None:
    """Require a valid in-memory session and double-submit token for mutations."""
    if request.method not in UNSAFE_METHODS:
        return None
    record = sessions.authenticate(
        request.cookies.get(SESSION_COOKIE),
        request.headers.get(CSRF_HEADER),
    )
    if record is None:
        return _error(status.HTTP_403_FORBIDDEN, "valid session and CSRF token required")
    request.state.actor_id = record.actor_id
    return None


def require_session(request: Request) -> SessionRecord:
    """Resolve a valid browser session for actor-owned read operations."""
    sessions: SessionStore = request.app.state.sessions
    record = sessions.get(request.cookies.get(SESSION_COOKIE))
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid local session required",
        )
    request.state.actor_id = record.actor_id
    return record


def _is_allowed_origin(origin: str, settings: Settings) -> bool:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return False
    allowed_ports = FRONTEND_PORTS | {settings.port}
    return (
        parsed.scheme == "http"
        and parsed.hostname == settings.host
        and parsed.username is None
        and parsed.password is None
        and port in allowed_ports
        and parsed.path == ""
        and parsed.query == ""
        and parsed.fragment == ""
    )


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})
