"""Actor-isolated task creation, progress, control, and result APIs."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel
from starlette.datastructures import FormData, UploadFile
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse

from localface_studio.api.security import require_session
from localface_studio.application.task_creation import (
    CONSENT_VERSION,
    AuthorizationRequiredError,
    TaskCreationService,
    TaskLimitExceededError,
    utc_now,
)
from localface_studio.application.task_queue import (
    TERMINAL_STATUSES,
    SingleTaskQueue,
    TaskEvent,
    TaskEventBroker,
)
from localface_studio.application.task_repository import TaskRepository
from localface_studio.domain.images import ImageUploadError, ValidatedImage
from localface_studio.domain.tasks import (
    OutputFormat,
    RetentionOption,
    TaskRecord,
    TaskStatus,
    transition_task,
)
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

router = APIRouter(tags=["tasks"])


class TaskImageResponse(BaseModel):
    image_format: str
    width: int
    height: int


class CreatedTaskResponse(BaseModel):
    task_id: str
    status: str
    expires_at: datetime
    consent_version: str
    output_format: str
    jpeg_quality: int
    watermark_enabled: bool
    source: TaskImageResponse
    target: TaskImageResponse


class TaskResponse(BaseModel):
    task_id: str
    status: str
    current_node: str | None
    error_code: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    output_format: str
    jpeg_quality: int
    watermark_enabled: bool


@router.post("/tasks", response_model=CreatedTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(request: Request) -> CreatedTaskResponse | JSONResponse:
    """Validate exactly two images and create one actor-owned queued task."""
    async with request.form(max_files=2, max_fields=5, max_part_size=16 * 1024) as form:
        try:
            source = _upload(form, "source")
            target = _upload(form, "target")
            authorization_confirmed = _boolean(form, "authorization_confirmed", False)
            output_format = OutputFormat(_text(form, "output_format", OutputFormat.PNG.value))
            jpeg_quality = _integer(form, "jpeg_quality", 95, minimum=5, maximum=100)
            watermark_enabled = _boolean(form, "watermark_enabled", True)
            retention = RetentionOption(
                _text(form, "retention", RetentionOption.THIRTY_MINUTES.value)
            )
        except ValueError as error:
            return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_form", str(error))

        service: TaskCreationService = request.app.state.task_creation
        try:
            created = await service.create(
                actor_id=request.state.actor_id,
                source=source,
                target=target,
                authorization_confirmed=authorization_confirmed,
                output_format=output_format,
                jpeg_quality=jpeg_quality,
                watermark_enabled=watermark_enabled,
                retention=retention,
            )
        except AuthorizationRequiredError as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "authorization_required",
                str(error),
            )
        except TaskLimitExceededError as error:
            return _error(status.HTTP_429_TOO_MANY_REQUESTS, "task_limit_exceeded", str(error))
        except ImageUploadError as error:
            return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, error.code, str(error))

    queue: SingleTaskQueue = request.app.state.task_queue
    try:
        await queue.enqueue(created.task)
    except RuntimeError:
        await queue.cancel(created.task.task_id, created.task.actor_id)
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "task_queue_unavailable",
            "Task execution is temporarily unavailable.",
        )

    return CreatedTaskResponse(
        task_id=created.task.task_id,
        status=created.task.status.value,
        expires_at=created.task.expires_at,
        consent_version=CONSENT_VERSION,
        output_format=created.task.output_format.value,
        jpeg_quality=created.task.jpeg_quality,
        watermark_enabled=created.task.watermark_enabled,
        source=_image_response(created.images.source),
        target=_image_response(created.images.target),
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, request: Request) -> TaskResponse | JSONResponse:
    """Return a privacy-safe task snapshot owned by the current session."""
    task = _owned_task(task_id, request)
    if task is None:
        return _not_found()
    return _task_response(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str, request: Request) -> TaskResponse | JSONResponse:
    """Request cancellation without revealing tasks owned by other actors."""
    queue: SingleTaskQueue = request.app.state.task_queue
    task = await queue.cancel(task_id, request.state.actor_id)
    if task is None:
        return _not_found()
    return _task_response(task)


@router.get("/tasks/{task_id}/events", response_model=None)
async def stream_task_events(
    task_id: str,
    request: Request,
    after_version: Annotated[int, Query(ge=-1)] = -1,
) -> StreamingResponse | JSONResponse:
    """Stream bounded task revisions as Server-Sent Events."""
    task = _owned_task(task_id, request)
    if task is None:
        return _not_found()
    broker: TaskEventBroker = request.app.state.task_events

    async def generate() -> AsyncIterator[str]:
        last_version = after_version
        async with broker.subscribe(task_id) as subscriber:
            history = broker.history(task_id, after_version=last_version)
            if not history:
                history = (TaskEvent.from_record(task),)
            for event in history:
                if event.version <= last_version:
                    continue
                last_version = event.version
                yield _sse(event)
                if event.status in TERMINAL_STATUSES:
                    return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(subscriber.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event.version <= last_version:
                    continue
                last_version = event.version
                yield _sse(event)
                if event.status in TERMINAL_STATUSES:
                    return

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/tasks/{task_id}/result", response_model=None)
def download_result(task_id: str, request: Request) -> FileResponse | JSONResponse:
    """Download a successful result through a fixed server-controlled path."""
    task = _owned_task(task_id, request)
    if task is None:
        return _not_found()
    if task.status is not TaskStatus.SUCCEEDED:
        return _error(status.HTTP_409_CONFLICT, "result_not_ready", "Result is not available.")
    workspaces: TaskWorkspaceStore = request.app.state.task_workspaces
    result_path = workspaces.result_path(task.task_id, task.output_format)
    if not result_path.is_file():
        return _error(status.HTTP_409_CONFLICT, "result_missing", "Result is not available.")
    media_type = "image/jpeg" if task.output_format is OutputFormat.JPEG else "image/png"
    suffix = "jpg" if task.output_format is OutputFormat.JPEG else "png"
    return FileResponse(
        path=result_path,
        media_type=media_type,
        filename=f"localface-simulation.{suffix}",
        headers={"Cache-Control": "no-store"},
    )


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_task(task_id: str, request: Request) -> Response | JSONResponse:
    """Delete files and mark a terminal task deleted using optimistic revisioning."""
    task = _owned_task(task_id, request)
    if task is None:
        return _not_found()
    if task.status is TaskStatus.DELETED:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if task.status not in TERMINAL_STATUSES:
        return _error(
            status.HTTP_409_CONFLICT,
            "task_not_terminal",
            "Cancel the task before deleting it.",
        )
    deleted = transition_task(
        task,
        TaskStatus.DELETED,
        at=utc_now(),
        current_node=task.current_node,
    )
    repository: TaskRepository = request.app.state.task_repository
    repository.save(deleted, expected_version=task.version)
    workspaces: TaskWorkspaceStore = request.app.state.task_workspaces
    workspaces.remove(task.task_id)
    events: TaskEventBroker = request.app.state.task_events
    events.publish(deleted)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _upload(form: FormData, field: str) -> UploadFile:
    value = form.get(field)
    if not isinstance(value, UploadFile):
        raise ValueError(f"{field} image is required")
    return value


def _text(form: FormData, field: str, default: str) -> str:
    value = form.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    return value


def _boolean(form: FormData, field: str, default: bool) -> bool:
    value = _text(form, field, str(default).lower()).casefold()
    if value not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false")
    return value == "true"


def _integer(
    form: FormData,
    field: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _text(form, field, str(default))
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def _image_response(image: ValidatedImage) -> TaskImageResponse:
    return TaskImageResponse(
        image_format=image.image_format.value,
        width=image.width,
        height=image.height,
    )


def _error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "detail": detail})


def _owned_task(task_id: str, request: Request) -> TaskRecord | None:
    session = require_session(request)
    repository: TaskRepository = request.app.state.task_repository
    return repository.get_for_actor(task_id, session.actor_id)


def _not_found() -> JSONResponse:
    return _error(status.HTTP_404_NOT_FOUND, "task_not_found", "Task not found.")


def _task_response(task: TaskRecord) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        current_node=task.current_node.value if task.current_node is not None else None,
        error_code=task.error_code,
        version=task.version,
        created_at=task.created_at,
        updated_at=task.updated_at,
        expires_at=task.expires_at,
        output_format=task.output_format.value,
        jpeg_quality=task.jpeg_quality,
        watermark_enabled=task.watermark_enabled,
    )


def _sse(event: TaskEvent) -> str:
    payload = {
        "task_id": event.task_id,
        "version": event.version,
        "status": event.status.value,
        "current_node": event.current_node.value if event.current_node is not None else None,
        "updated_at": event.updated_at.isoformat(),
        "error_code": event.error_code,
    }
    return f"id: {event.version}\nevent: task\ndata: {json.dumps(payload)}\n\n"
