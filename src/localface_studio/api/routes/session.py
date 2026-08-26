"""Local browser-session bootstrap endpoint."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from localface_studio.api.security import SESSION_COOKIE
from localface_studio.application.sessions import SessionStore
from localface_studio.infrastructure.sqlite_sessions import SESSION_LIFETIME

router = APIRouter(tags=["session"])


class SessionResponse(BaseModel):
    """Only the non-cookie CSRF credential is exposed to frontend memory."""

    csrf_token: str


@router.get("/session", response_model=SessionResponse)
def establish_session(request: Request, response: Response) -> SessionResponse:
    """Reuse a valid local session or create a restart-safe browser cookie."""
    sessions: SessionStore = request.app.state.sessions
    record = sessions.get(request.cookies.get(SESSION_COOKIE))
    if record is None:
        record = sessions.create()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=record.session_id,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/api",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionResponse(csrf_token=record.csrf_token)
