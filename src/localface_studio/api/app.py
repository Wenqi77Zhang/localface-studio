"""FastAPI application factory."""

from fastapi import FastAPI

from localface_studio import __version__
from localface_studio.api.routes.health import router as health_router


def create_app() -> FastAPI:
    """Create an isolated application instance for runtime and tests."""
    application = FastAPI(
        title="LocalFace Studio API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.include_router(health_router, prefix="/api/v1")
    return application
