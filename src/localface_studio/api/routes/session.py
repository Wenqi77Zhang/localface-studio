"""Local browser-session bootstrap endpoint."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from localface_studio.api.security import SESSION_COOKIE
from localface_studio.application.sessions import SessionStore

router = APIRouter(tags=["session"])


class SessionResponse(BaseModel):
    """Only the non-cookie CSRF credential is exposed to frontend memory."""

    csrf_token: str


@router.get("/session", response_model=SessionResponse)
def establish_session(request: Request, response: Response) -> SessionResponse:
    """Reuse a valid process-local session or create a browser-session cookie."""
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
        )
    response.headers["Cache-Control"] = "no-store"
    return SessionResponse(csrf_token=record.csrf_token)
