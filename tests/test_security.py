"""Host, Origin, browser-session, and CSRF integration tests."""

import asyncio
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI

from localface_studio.api.app import create_app
from localface_studio.api.security import CSRF_HEADER, require_session
from localface_studio.application.sessions import SessionRecord
from localface_studio.infrastructure.config import Settings

LOCAL_ORIGIN = "http://127.0.0.1:5173"


def security_test_app() -> FastAPI:
    app = create_app(Settings(log_level="CRITICAL"))

    def mutate() -> dict[str, bool]:
        return {"ok": True}

    def owned_read(
        session: Annotated[SessionRecord, Depends(require_session)],
    ) -> dict[str, str]:
        return {"actor_id": session.actor_id}

    app.add_api_route("/api/v1/test-mutation", mutate, methods=["POST"])
    app.add_api_route("/api/v1/test-owned", owned_read, methods=["GET"])
    return app


def test_session_cookie_is_http_only_strict_and_reused() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=security_test_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            first = await client.get("/api/v1/session")
            second = await client.get("/api/v1/session")

        cookie = first.headers["set-cookie"].lower()
        assert first.status_code == 200
        assert first.json()["csrf_token"] == second.json()["csrf_token"]
        assert "localface_session=" in cookie
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "path=/api" in cookie
        assert "max-age" not in cookie
        assert first.headers["cache-control"] == "no-store"
        assert "session_id" not in first.text
        assert "actor_id" not in first.text

    asyncio.run(scenario())


def test_host_and_cross_site_requests_are_rejected() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=security_test_app())
        async with httpx.AsyncClient(transport=transport) as client:
            invalid_host = await client.get("http://attacker.example/api/v1/health")
            cross_site = await client.get(
                "http://127.0.0.1/api/v1/session",
                headers={"Sec-Fetch-Site": "cross-site"},
            )

        assert invalid_host.status_code == 400
        assert invalid_host.json() == {"detail": "invalid request host"}
        assert cross_site.status_code == 403
        assert cross_site.json() == {"detail": "cross-site requests are not allowed"}

    asyncio.run(scenario())


def test_mutation_requires_allowed_origin_session_and_csrf() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=security_test_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            session = await client.get("/api/v1/session")
            token = session.json()["csrf_token"]
            missing_origin = await client.post(
                "/api/v1/test-mutation",
                headers={CSRF_HEADER: token},
            )
            wrong_origin = await client.post(
                "/api/v1/test-mutation",
                headers={"Origin": "http://attacker.example", CSRF_HEADER: token},
            )
            missing_csrf = await client.post(
                "/api/v1/test-mutation",
                headers={"Origin": LOCAL_ORIGIN},
            )
            accepted = await client.post(
                "/api/v1/test-mutation",
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: token},
            )

        assert missing_origin.status_code == 403
        assert wrong_origin.status_code == 403
        assert missing_csrf.status_code == 403
        assert accepted.status_code == 200
        assert accepted.json() == {"ok": True}

    asyncio.run(scenario())


def test_actor_owned_read_requires_live_session_and_restart_invalidates_it() -> None:
    async def scenario() -> None:
        first_app = security_test_app()
        first_transport = httpx.ASGITransport(app=first_app)
        async with httpx.AsyncClient(
            transport=first_transport,
            base_url="http://127.0.0.1",
        ) as client:
            rejected = await client.get("/api/v1/test-owned")
            await client.get("/api/v1/session")
            accepted = await client.get("/api/v1/test-owned")
            old_cookie = client.cookies.get("localface_session")

        assert old_cookie is not None
        restarted_transport = httpx.ASGITransport(app=security_test_app())
        async with httpx.AsyncClient(
            transport=restarted_transport,
            base_url="http://127.0.0.1",
            cookies={"localface_session": old_cookie},
        ) as restarted_client:
            after_restart = await restarted_client.get("/api/v1/test-owned")

        assert rejected.status_code == 401
        assert accepted.status_code == 200
        assert accepted.json()["actor_id"]
        assert after_restart.status_code == 401

    asyncio.run(scenario())
