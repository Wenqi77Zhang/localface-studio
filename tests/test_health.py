"""API contract and request-log privacy tests."""

import asyncio
import json
import logging

import httpx

from localface_studio.api.app import create_app
from localface_studio.infrastructure.config import Settings


def test_health_contract_and_query_is_not_logged(capsys) -> None:  # type: ignore[no-untyped-def]
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(Settings(log_level="INFO")))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            return await client.get("/api/v1/health?token=must-not-appear")

    response = asyncio.run(request_health())
    captured = capsys.readouterr()
    log_record = json.loads(captured.err.strip())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == log_record["request_id"]
    assert log_record["event"] == "request_completed"
    assert log_record["route"] == "/health"
    assert "must-not-appear" not in captured.err
    assert "token" not in captured.err
    assert logging.getLogger("localface").propagate is False
