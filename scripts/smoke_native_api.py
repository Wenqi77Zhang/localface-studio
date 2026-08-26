"""Exercise the complete local HTTP workflow with explicitly authorized images."""

import argparse
import asyncio
import shutil
from pathlib import Path
from time import monotonic
from typing import Any

import httpx

from localface_studio.api.app import create_app
from localface_studio.api.security import CSRF_HEADER
from localface_studio.infrastructure.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:5173"
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}


def main() -> None:
    args = parse_args()
    if not args.confirm_image_authorization or not args.accept_research_license:
        raise SystemExit("Pass both --confirm-image-authorization and --accept-research-license.")
    source = Path(args.source).resolve()
    target = Path(args.target).resolve()
    if not source.is_file() or not target.is_file():
        raise SystemExit("Source and target images must exist.")
    output = Path(args.output).resolve()
    asyncio.run(run_workflow(source, target, output, args.detector_id))


async def run_workflow(
    source: Path,
    target: Path,
    output: Path,
    detector_id: str,
) -> None:
    runtime = ROOT / ".tools" / "native-api-smoke"
    if runtime.exists():
        shutil.rmtree(runtime)
    app = create_app(
        Settings(
            log_level="WARNING",
            runtime_directory=runtime,
            workflow_backend="native-research",
            task_timeout_seconds=300,
        )
    )
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1",
            ) as client:
                session = await client.get("/api/v1/session")
                session.raise_for_status()
                csrf = str(session.json()["csrf_token"])
                source_revision = await detect(client, csrf, source, "source", detector_id)
                target_revision = await detect(client, csrf, target, "target", detector_id)
                task_id = await create_task(
                    client,
                    csrf,
                    source,
                    target,
                    source_revision,
                    target_revision,
                )
                state = await wait_for_task(client, task_id)
                if state["status"] != "succeeded":
                    raise RuntimeError(
                        f"Native API smoke failed: {state['status']} / {state['error_code']}"
                    )
                result = await client.get(f"/api/v1/tasks/{task_id}/result")
                result.raise_for_status()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(result.content)
                capabilities = (await client.get("/api/v1/capabilities")).json()
                print(
                    "Native API workflow succeeded: "
                    f"{output.name}; provider={capabilities['execution_provider']}"
                )
    finally:
        if runtime.exists():
            shutil.rmtree(runtime)


async def detect(
    client: httpx.AsyncClient,
    csrf: str,
    image: Path,
    role: str,
    detector_id: str,
) -> dict[str, Any]:
    with image.open("rb") as stream:
        response = await client.post(
            "/api/v1/face-detections",
            data={
                "role": role,
                "detector_id": detector_id,
                "research_license_accepted": "true",
            },
            files={"image": (image.name, stream, media_type(image))},
            headers={"Origin": ORIGIN, CSRF_HEADER: csrf},
        )
    response.raise_for_status()
    revision: dict[str, Any] = response.json()
    faces = revision.get("faces")
    if not isinstance(faces, list) or not faces:
        raise RuntimeError(f"No face detected in {role} image.")
    selected = revision.get("selected_detection_id")
    if selected is None:
        selected = faces[0]["detection_id"]
        selection = await client.post(
            f"/api/v1/face-detections/{revision['revision_id']}/selection",
            json={"detection_id": selected},
            headers={"Origin": ORIGIN, CSRF_HEADER: csrf},
        )
        selection.raise_for_status()
        revision = selection.json()
    return revision


async def create_task(
    client: httpx.AsyncClient,
    csrf: str,
    source: Path,
    target: Path,
    source_revision: dict[str, Any],
    target_revision: dict[str, Any],
) -> str:
    data = {
        "source_revision_id": source_revision["revision_id"],
        "source_detection_id": source_revision["selected_detection_id"],
        "target_revision_id": target_revision["revision_id"],
        "target_detection_id": target_revision["selected_detection_id"],
        "authorization_confirmed": "true",
        "research_model_license_accepted": "true",
        "output_format": "png",
        "jpeg_quality": "95",
        "watermark_enabled": "true",
        "retention": "30m",
    }
    with source.open("rb") as source_stream, target.open("rb") as target_stream:
        response = await client.post(
            "/api/v1/tasks",
            data=data,
            files={
                "source": (source.name, source_stream, media_type(source)),
                "target": (target.name, target_stream, media_type(target)),
            },
            headers={"Origin": ORIGIN, CSRF_HEADER: csrf},
        )
    response.raise_for_status()
    return str(response.json()["task_id"])


async def wait_for_task(client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
    deadline = monotonic() + 310
    while monotonic() < deadline:
        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        state: dict[str, Any] = response.json()
        if state.get("status") in TERMINAL_STATUSES:
            return state
        await asyncio.sleep(0.25)
    raise TimeoutError("Native API smoke did not reach a terminal task state.")


def media_type(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.casefold(), "application/octet-stream")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--detector-id",
        choices=["yunet-opencv", "scrfd-insightface-research"],
        default="yunet-opencv",
    )
    parser.add_argument("--confirm-image-authorization", action="store_true")
    parser.add_argument("--accept-research-license", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
