"""Artifact selection, thumbnails, strict expiry and retryable deletion contracts."""

import asyncio
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from localface_studio.api.app import create_app
from localface_studio.api.routes import tasks as task_routes
from localface_studio.api.security import CSRF_HEADER
from localface_studio.infrastructure.config import Settings
from tests.test_task_api import (
    LOCAL_ORIGIN,
    authorize_task_form,
    establish_session,
    running_client,
    task_form,
)
from tests.test_task_control_api import wait_for_status


def test_variant_thumbnails_expiry_isolation_and_retryable_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(
                workflow_backend="simulation",
                log_level="CRITICAL",
                runtime_directory=tmp_path / "runtime",
            )
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            data, files = task_form()
            await authorize_task_form(app, client, data, files)
            created = await client.post(
                "/api/v1/tasks",
                data=data,
                files=files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            identifier = created.json()["task_id"]
            await wait_for_status(client, identifier, "succeeded")
            root = f"/api/v1/tasks/{identifier}"
            # Explicitly injected test artifacts. This test does not claim model quality.
            workspace = tmp_path / "runtime/tasks" / identifier
            Image.new("RGB", (2048, 512), (20, 40, 60)).save(workspace / "base.png")
            Image.new("RGB", (2048, 512), (70, 80, 90)).save(workspace / "enhanced.png")
            (workspace / "metrics.json").write_text(
                '{"duration_ms":12,"secret":"no"}', encoding="utf-8"
            )
            artifacts = (await client.get(root + "/artifacts")).json()
            assert artifacts["variants"] == ["base", "enhanced"]
            assert artifacts["metrics"] == {"duration_ms": 12}
            base = await client.get(root + "/result?variant=base")
            enhanced = await client.get(root + "/result?variant=enhanced")
            assert base.content != enhanced.content
            assert (await client.get(root + "/result")).content == enhanced.content
            thumb = await client.get(root + "/thumbnail?variant=base")
            with Image.open(BytesIO(thumb.content)) as image:
                assert image.size == (480, 120)
            assert thumb.headers["cache-control"] == "no-store"
            assert (await client.get(root + "/result?variant=../../source")).status_code == 422
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=LOCAL_ORIGIN
            ) as other:
                await establish_session(other)
                for suffix in ("/artifacts", "/result?variant=base", "/thumbnail"):
                    assert (await other.get(root + suffix)).status_code == 404
            with monkeypatch.context() as patch:
                patch.setattr(task_routes, "utc_now", lambda: datetime.now(UTC) + timedelta(days=1))
                for suffix in ("/artifacts", "/result?variant=base", "/thumbnail"):
                    assert (await client.get(root + suffix)).status_code == 409
            remove = app.state.task_workspaces.remove

            def busy(_: str) -> None:
                raise PermissionError("busy")

            monkeypatch.setattr(app.state.task_workspaces, "remove", busy)
            headers = {"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf}
            assert (await client.delete(root, headers=headers)).status_code == 503
            assert (await client.get(root)).json()["status"] == "succeeded"
            monkeypatch.setattr(app.state.task_workspaces, "remove", remove)
            assert (await client.delete(root, headers=headers)).status_code == 204
            assert not workspace.exists()
            assert (await client.get(root + "/artifacts")).status_code == 409

    asyncio.run(scenario())
