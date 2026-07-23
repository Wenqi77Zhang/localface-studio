"""Task creation API tests using generated geometric images only."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from localface_studio.api.app import create_app
from localface_studio.api.security import CSRF_HEADER, MAXIMUM_TASK_REQUEST_BYTES
from localface_studio.application.task_creation import CONSENT_VERSION
from localface_studio.application.task_queue import NodeReporter
from localface_studio.domain.tasks import TaskRecord, TaskStatus, WorkflowNode
from localface_studio.infrastructure.config import Settings

LOCAL_ORIGIN = "http://127.0.0.1:5173"


@asynccontextmanager
async def running_client(app) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            yield client


class BlockingBackend:
    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        for node in WorkflowNode:
            await report_node(node)
            if node is WorkflowNode.VALIDATE:
                await self.release.wait()


def png_bytes(*, size: tuple[int, int] = (20, 16)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=(20, 100, 180)).save(buffer, format="PNG")
    return buffer.getvalue()


def task_form(
    *,
    authorization: str = "true",
    output_format: str = "png",
    jpeg_quality: str = "95",
    watermark: str = "true",
    retention: str = "30m",
    target: bytes | None = None,
) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
    data = {
        "authorization_confirmed": authorization,
        "output_format": output_format,
        "jpeg_quality": jpeg_quality,
        "watermark_enabled": watermark,
        "retention": retention,
    }
    files = {
        "source": ("private-source.png", png_bytes(), "image/png"),
        "target": ("private-target.png", target or png_bytes(size=(24, 18)), "image/png"),
    }
    return data, files


async def establish_session(client: httpx.AsyncClient) -> str:
    response = await client.get("/api/v1/session")
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def test_task_creation_persists_minimal_metadata_and_canonical_files(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"))
        async with running_client(app) as client:
            csrf = await establish_session(client)
            data, files = task_form(
                output_format="jpeg",
                jpeg_quality="73",
                watermark="false",
                retention="24h",
            )
            response = await client.post(
                "/api/v1/tasks",
                data=data,
                files=files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            session_id = client.cookies.get("localface_session")

        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "queued"
        assert payload["consent_version"] == CONSENT_VERSION
        assert payload["output_format"] == "jpeg"
        assert payload["jpeg_quality"] == 73
        assert payload["watermark_enabled"] is False
        assert payload["source"] == {"image_format": "png", "width": 20, "height": 16}
        assert payload["target"] == {"image_format": "png", "width": 24, "height": 18}
        assert "private-source" not in response.text
        assert "actor_id" not in response.text
        assert "runtime" not in response.text

        session = app.state.sessions.get(session_id)
        assert session is not None
        stored = app.state.task_repository.get_for_actor(payload["task_id"], session.actor_id)
        assert stored is not None
        assert stored.status is TaskStatus.SUCCEEDED
        assert stored.consent_version == CONSENT_VERSION
        assert stored.jpeg_quality == 73
        assert datetime.fromisoformat(payload["expires_at"]) - stored.created_at == timedelta(
            hours=24
        )
        workspace = tmp_path / "runtime" / "tasks" / payload["task_id"]
        assert {path.name for path in workspace.iterdir()} == {
            "source.png",
            "target.png",
            "result.jpg",
        }

    asyncio.run(scenario())


def test_authorization_and_invalid_image_fail_without_task_artifacts(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"))
        async with running_client(app) as client:
            csrf = await establish_session(client)
            denied_data, denied_files = task_form(authorization="false")
            denied = await client.post(
                "/api/v1/tasks",
                data=denied_data,
                files=denied_files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            invalid_data, invalid_files = task_form(target=b"not-an-image")
            invalid = await client.post(
                "/api/v1/tasks",
                data=invalid_data,
                files=invalid_files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            quality_data, quality_files = task_form(jpeg_quality="101")
            invalid_quality = await client.post(
                "/api/v1/tasks",
                data=quality_data,
                files=quality_files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            retention_data, retention_files = task_form(retention="7d")
            invalid_retention = await client.post(
                "/api/v1/tasks",
                data=retention_data,
                files=retention_files,
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )

        assert denied.status_code == 422
        assert denied.json()["code"] == "authorization_required"
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_image"
        assert invalid_quality.status_code == 422
        assert invalid_quality.json()["code"] == "invalid_form"
        assert invalid_retention.status_code == 422
        assert invalid_retention.json()["code"] == "invalid_form"
        task_root = tmp_path / "runtime" / "tasks"
        assert list(task_root.iterdir()) == []

    asyncio.run(scenario())


def test_fourth_unfinished_task_is_rejected_for_same_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = BlockingBackend()
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            workflow_backend=backend,
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            responses = []
            for _ in range(4):
                data, files = task_form()
                responses.append(
                    await client.post(
                        "/api/v1/tasks",
                        data=data,
                        files=files,
                        headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
                    )
                )
            backend.release.set()

        assert [response.status_code for response in responses] == [201, 201, 201, 429]
        assert responses[-1].json()["code"] == "task_limit_exceeded"
        assert len(list((tmp_path / "runtime" / "tasks").iterdir())) == 3

    asyncio.run(scenario())


def test_task_request_requires_bounded_multipart_content_length(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = create_app(Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"))
        async with running_client(app) as client:
            csrf = await establish_session(client)
            common_headers = {"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf}

            missing_length_request = client.build_request(
                "POST",
                "/api/v1/tasks",
                content=b"--boundary--",
                headers={
                    **common_headers,
                    "Content-Type": "multipart/form-data; boundary=boundary",
                },
            )
            del missing_length_request.headers["Content-Length"]
            missing_length = await client.send(missing_length_request)

            oversized = await client.post(
                "/api/v1/tasks",
                content=b"x",
                headers={
                    **common_headers,
                    "Content-Type": "multipart/form-data; boundary=boundary",
                    "Content-Length": str(MAXIMUM_TASK_REQUEST_BYTES + 1),
                },
            )
            wrong_media = await client.post(
                "/api/v1/tasks",
                content=b"{}",
                headers={**common_headers, "Content-Type": "application/json"},
            )

        assert missing_length.status_code == 411
        assert oversized.status_code == 413
        assert wrong_media.status_code == 415

    asyncio.run(scenario())
