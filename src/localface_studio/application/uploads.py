"""Chunked upload orchestration independent of FastAPI and Pillow."""

from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from localface_studio.domain.images import (
    ImageFormat,
    ImageLimits,
    ImageRole,
    ImageUploadError,
    UploadedImagePair,
    ValidatedImage,
)

CHUNK_SIZE = 64 * 1024


class AsyncUpload(Protocol):
    """Small structural contract implemented by FastAPI's UploadFile."""

    @property
    def filename(self) -> str | None:
        """Untrusted display name used only for suffix validation."""
        ...

    @property
    def content_type(self) -> str | None:
        """Untrusted declared media type checked against decoded content."""
        ...

    def read(self, size: int = -1) -> Awaitable[bytes]:
        """Read at most size bytes from the spooled upload."""
        ...


class WorkspaceStore(Protocol):
    """Filesystem boundary for random task workspaces."""

    def create(self, task_id: str) -> Path:
        """Create and return a new isolated workspace."""
        ...

    def staging_path(self, task_id: str, role: ImageRole) -> Path:
        """Return the fixed temporary path for one image role."""
        ...

    def finalize(
        self,
        task_id: str,
        role: ImageRole,
        staging_path: Path,
        extension: str,
    ) -> str:
        """Atomically rename a validated image and return its canonical name."""
        ...

    def remove(self, task_id: str) -> None:
        """Delete a workspace after validation failure."""
        ...


class ImageValidator(Protocol):
    """Content-level image validation boundary."""

    def validate(
        self,
        path: Path,
        *,
        original_filename: str | None,
        declared_content_type: str | None,
    ) -> tuple[str, int, int, str]:
        """Return canonical extension, width, height, and mode."""
        ...


class TaskUploadService:
    """Store and validate a source-target pair with all-or-nothing cleanup."""

    def __init__(
        self,
        workspace_store: WorkspaceStore,
        validator: ImageValidator,
        *,
        limits: ImageLimits | None = None,
    ) -> None:
        self._workspace_store = workspace_store
        self._validator = validator
        self._limits = limits or ImageLimits()

    async def save_pair(
        self,
        task_id: str,
        source: AsyncUpload,
        target: AsyncUpload,
    ) -> UploadedImagePair:
        """Stream two files into a new workspace and roll back either-file failure."""
        self._workspace_store.create(task_id)
        try:
            source_image = await self._save_one(task_id, ImageRole.SOURCE, source)
            target_image = await self._save_one(task_id, ImageRole.TARGET, target)
        except BaseException:
            with suppress(Exception):
                self._workspace_store.remove(task_id)
            raise
        return UploadedImagePair(task_id=task_id, source=source_image, target=target_image)

    def discard(self, task_id: str) -> None:
        """Remove a task workspace when a later database operation fails."""
        self._workspace_store.remove(task_id)

    async def _save_one(
        self,
        task_id: str,
        role: ImageRole,
        upload: AsyncUpload,
    ) -> ValidatedImage:
        staging_path = self._workspace_store.staging_path(task_id, role)
        byte_count = await self._write_chunks(staging_path, upload.read)
        extension, width, height, mode = self._validator.validate(
            staging_path,
            original_filename=upload.filename,
            declared_content_type=upload.content_type,
        )
        stored_name = self._workspace_store.finalize(
            task_id,
            role,
            staging_path,
            extension,
        )
        return ValidatedImage(
            role=role,
            image_format=ImageFormat(extension),
            width=width,
            height=height,
            mode=mode,
            byte_count=byte_count,
            stored_name=stored_name,
        )

    async def _write_chunks(
        self,
        destination: Path,
        read: Callable[[int], Awaitable[bytes]],
    ) -> int:
        byte_count = 0
        with destination.open("xb") as output:
            while chunk := await read(CHUNK_SIZE):
                byte_count += len(chunk)
                if byte_count > self._limits.maximum_bytes:
                    raise ImageUploadError(
                        "file_too_large",
                        "Each image must be 25 MB or smaller.",
                    )
                output.write(chunk)
        if byte_count == 0:
            raise ImageUploadError("empty_file", "Uploaded images must not be empty.")
        return byte_count
