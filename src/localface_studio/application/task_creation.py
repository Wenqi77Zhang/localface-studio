"""Atomic task creation across authorization, uploads, and metadata storage."""

from asyncio import Lock
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from localface_studio.application.detection_revisions import TaskSelectionVerifier
from localface_studio.application.task_repository import TaskRepository
from localface_studio.application.uploads import AsyncUpload, TaskUploadService
from localface_studio.domain.images import UploadedImagePair
from localface_studio.domain.tasks import (
    OutputFormat,
    RetentionOption,
    TaskRecord,
    TaskStatus,
    new_task_id,
)

CONSENT_VERSION = "2026-07-23-v1"
MAXIMUM_UNFINISHED_TASKS = 3


class AuthorizationRequiredError(ValueError):
    """Raised when the per-task image authorization was not confirmed."""


class TaskLimitExceededError(RuntimeError):
    """Raised when one actor already owns the allowed unfinished task count."""


@dataclass(frozen=True, slots=True)
class CreatedTask:
    """New queued task and its privacy-safe image facts."""

    task: TaskRecord
    images: UploadedImagePair


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskCreationService:
    """Serialize local task creation so the per-session limit cannot race."""

    def __init__(
        self,
        repository: TaskRepository,
        uploads: TaskUploadService,
        selection_verifier: TaskSelectionVerifier,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._uploads = uploads
        self._selection_verifier = selection_verifier
        self._clock = clock
        self._creation_lock = Lock()

    async def create(
        self,
        *,
        actor_id: str,
        source: AsyncUpload,
        target: AsyncUpload,
        authorization_confirmed: bool,
        output_format: OutputFormat,
        jpeg_quality: int,
        watermark_enabled: bool,
        retention: RetentionOption,
        source_revision_id: str,
        source_detection_id: str,
        target_revision_id: str,
        target_detection_id: str,
    ) -> CreatedTask:
        """Create one queued task or leave neither files nor metadata behind."""
        if not authorization_confirmed:
            raise AuthorizationRequiredError("Image authorization must be confirmed.")

        async with self._creation_lock:
            if self._repository.count_unfinished_for_actor(actor_id) >= MAXIMUM_UNFINISHED_TASKS:
                raise TaskLimitExceededError("Too many unfinished tasks.")

            task_id = new_task_id()
            images = await self._uploads.save_pair(task_id, source, target)
            try:
                selection = await self._selection_verifier.verify(
                    task_id=task_id,
                    actor_id=actor_id,
                    source_revision_id=source_revision_id,
                    source_detection_id=source_detection_id,
                    target_revision_id=target_revision_id,
                    target_detection_id=target_detection_id,
                )
                now = self._clock()
                task = TaskRecord(
                    task_id=task_id,
                    actor_id=actor_id,
                    status=TaskStatus.QUEUED,
                    created_at=now,
                    updated_at=now,
                    expires_at=now + retention.duration,
                    consent_version=CONSENT_VERSION,
                    consented_at=now,
                    output_format=output_format,
                    jpeg_quality=jpeg_quality,
                    watermark_enabled=watermark_enabled,
                    detector_id=selection.detector_id,
                    source_detection_id=selection.source_detection_id,
                    target_detection_id=selection.target_detection_id,
                )
                self._repository.create(task)
            except Exception:
                self._uploads.discard(task_id)
                raise
            return CreatedTask(task=task, images=images)
