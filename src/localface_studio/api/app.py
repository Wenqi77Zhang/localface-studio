"""FastAPI application factory."""

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from localface_studio import __version__
from localface_studio.api.routes.health import router as health_router
from localface_studio.api.routes.session import router as session_router
from localface_studio.api.security import reject_invalid_csrf, reject_untrusted_source
from localface_studio.application.sessions import SessionStore
from localface_studio.infrastructure.config import Settings, get_settings
from localface_studio.infrastructure.logging import configure_logging, log_event


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated application instance for runtime and tests."""
    runtime_settings = settings or get_settings()
    logger = configure_logging(runtime_settings.log_level)
    application = FastAPI(
        title="LocalFace Studio API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.state.settings = runtime_settings
    application.state.sessions = SessionStore()
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(session_router, prefix="/api/v1")

    @application.middleware("http")
    async def local_request_security(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Apply source validation before session and CSRF validation."""
        rejection = reject_untrusted_source(request, runtime_settings)
        if rejection is None:
            rejection = reject_invalid_csrf(request, application.state.sessions)
        if rejection is not None:
            return rejection
        return await call_next(request)

    @application.middleware("http")
    async def privacy_safe_request_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Log bounded request metadata without headers, query values, or bodies."""
        request_id = uuid4().hex
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as error:
            log_event(
                logger,
                logging.ERROR,
                "request_failed",
                request_id=request_id,
                method=request.method,
                route="unresolved",
                status_code=500,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                error_type=type(error).__name__,
            )
            raise

        route = request.scope.get("route")
        route_template = getattr(route, "path", "unresolved")
        log_event(
            logger,
            logging.INFO,
            "request_completed",
            request_id=request_id,
            method=request.method,
            route=route_template,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        response.headers["X-Request-ID"] = request_id
        return response

    return application
