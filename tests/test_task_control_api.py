"""Actor-isolated task status, events, cancellation, download, and deletion tests."""

import asyncio
import json
from pathlib import Path
from typing import cast

import httpx
from PIL import Image

from localface_studio.api.app import create_app
from localface_studio.api.security import CSRF_HEADER
from localface_studio.infrastructure.config import Settings
from tests.test_task_api import (
    LOCAL_ORIGIN,
    BlockingBackend,
    establish_session,
    running_client,
    task_form,
)


async def wait_for_status(
    client: httpx.AsyncClient,
    task_id: str,
    expected: str,
) -> dict[str, object]:
    for _ in range(100):
        response = await client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected:
            return cast(dict[str, object], payload)
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not reach {expected}")


def test_success_events_download_actor_isolation_and_delete(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"))
        async with running_client(app) as owner:
            csrf = await establish_session(owner)
            data, files = task_form()
            created = await owner.post(
                "/api/v1/tasks",
                data=data,
                files=files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            assert created.status_code == 201
            task_id = created.json()["task_id"]
            succeeded = await wait_for_status(owner, task_id, "succeeded")
            assert succeeded["current_node"] == "export"
            assert "actor_id" not in succeeded

            events = await owner.get(f"/api/v1/tasks/{task_id}/events")
            assert events.status_code == 200
            event_payloads = [
                json.loads(line.removeprefix("data: "))
                for line in events.text.splitlines()
                if line.startswith("data: ")
            ]
            assert event_payloads[-1]["status"] == "succeeded"
            assert [event["version"] for event in event_payloads] == sorted(
                {event["version"] for event in event_payloads}
            )

            result = await owner.get(f"/api/v1/tasks/{task_id}/result")
            assert result.status_code == 200
            assert result.headers["content-type"] == "image/png"
            result_path = tmp_path / "downloaded-result.png"
            result_path.write_bytes(result.content)
            with Image.open(result_path) as image:
                image.load()
                assert image.size == (24, 18)

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as stranger:
                stranger_csrf = await establish_session(stranger)
                hidden = await stranger.get(f"/api/v1/tasks/{task_id}")
                hidden_delete = await stranger.delete(
                    f"/api/v1/tasks/{task_id}",
                    headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: stranger_csrf},
                )
                assert hidden.status_code == 404
                assert hidden_delete.status_code == 404

            deleted = await owner.delete(
                f"/api/v1/tasks/{task_id}",
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            assert deleted.status_code == 204
            assert not (tmp_path / "runtime" / "tasks" / task_id).exists()
            unavailable = await owner.get(f"/api/v1/tasks/{task_id}/result")
            assert unavailable.status_code == 409

    asyncio.run(scenario())


def test_running_task_must_be_cancelled_before_deletion(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = BlockingBackend()
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            workflow_backend=backend,
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            data, files = task_form()
            created = await client.post(
                "/api/v1/tasks",
                data=data,
                files=files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            task_id = created.json()["task_id"]
            await wait_for_status(client, task_id, "running")

            premature_delete = await client.delete(
                f"/api/v1/tasks/{task_id}",
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            assert premature_delete.status_code == 409
            assert premature_delete.json()["code"] == "task_not_terminal"

            cancellation = await client.post(
                f"/api/v1/tasks/{task_id}/cancel",
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            assert cancellation.status_code == 200
            await wait_for_status(client, task_id, "cancelled")
            assert not (tmp_path / "runtime" / "tasks" / task_id).exists()

            deleted = await client.delete(
                f"/api/v1/tasks/{task_id}",
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            assert deleted.status_code == 204

    asyncio.run(scenario())
