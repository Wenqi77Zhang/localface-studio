"""Task creation API with authorization, upload, and retention controls."""

from datetime import datetime

from fastapi import APIRouter, Request, status
from pydantic import BaseModel
from starlette.datastructures import FormData, UploadFile
from starlette.responses import JSONResponse

from localface_studio.application.task_creation import (
    CONSENT_VERSION,
    AuthorizationRequiredError,
    TaskCreationService,
    TaskLimitExceededError,
)
from localface_studio.domain.images import ImageUploadError, ValidatedImage
from localface_studio.domain.tasks import OutputFormat, RetentionOption

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
    watermark_enabled: bool
    source: TaskImageResponse
    target: TaskImageResponse


@router.post("/tasks", response_model=CreatedTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(request: Request) -> CreatedTaskResponse | JSONResponse:
    """Validate exactly two images and create one actor-owned queued task."""
    async with request.form(max_files=2, max_fields=4, max_part_size=16 * 1024) as form:
        try:
            source = _upload(form, "source")
            target = _upload(form, "target")
            authorization_confirmed = _boolean(form, "authorization_confirmed", False)
            output_format = OutputFormat(_text(form, "output_format", OutputFormat.PNG.value))
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

    return CreatedTaskResponse(
        task_id=created.task.task_id,
        status=created.task.status.value,
        expires_at=created.task.expires_at,
        consent_version=CONSENT_VERSION,
        output_format=created.task.output_format.value,
        watermark_enabled=created.task.watermark_enabled,
        source=_image_response(created.images.source),
        target=_image_response(created.images.target),
    )


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


def _image_response(image: ValidatedImage) -> TaskImageResponse:
    return TaskImageResponse(
        image_format=image.image_format.value,
        width=image.width,
        height=image.height,
    )


def _error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "detail": detail})
