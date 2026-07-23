"""ASGI application entry point."""

from localface_studio.api.app import create_app

app = create_app()
