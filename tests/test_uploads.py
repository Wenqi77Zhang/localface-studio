"""Programmatically generated, non-person image upload tests."""

import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from localface_studio.application.uploads import CHUNK_SIZE, TaskUploadService
from localface_studio.domain.images import ImageFormat, ImageLimits, ImageUploadError
from localface_studio.infrastructure.image_validation import PillowImageValidator
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

TASK_ID = "A" * 32


class FakeUpload:
    """Minimal in-memory implementation of the async upload protocol."""

    def __init__(self, data: bytes, filename: str, content_type: str) -> None:
        self.filename: str | None = filename
        self.content_type: str | None = content_type
        self._stream = BytesIO(data)
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._stream.read(size)


class CancelledUpload(FakeUpload):
    async def read(self, size: int = -1) -> bytes:
        raise asyncio.CancelledError


def image_bytes(
    image_format: str,
    *,
    size: tuple[int, int] = (16, 12),
    compress_level: int | None = None,
) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", size, color=(30, 90, 150))
    options = {"compress_level": compress_level} if compress_level is not None else {}
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


def animated_png_bytes() -> bytes:
    buffer = BytesIO()
    first = Image.new("RGBA", (8, 8), color=(255, 0, 0, 255))
    second = Image.new("RGBA", (8, 8), color=(0, 0, 255, 255))
    first.save(
        buffer,
        format="PNG",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    return buffer.getvalue()


def make_service(root: Path, limits: ImageLimits | None = None) -> TaskUploadService:
    active_limits = limits or ImageLimits()
    return TaskUploadService(
        TaskWorkspaceStore(root),
        PillowImageValidator(limits=active_limits),
        limits=active_limits,
    )


@pytest.mark.parametrize(
    ("encoded_format", "filename", "content_type", "expected_format", "stored_suffix"),
    [
        ("PNG", "source.png", "image/png", ImageFormat.PNG, ".png"),
        ("JPEG", "source.jpeg", "image/jpeg", ImageFormat.JPEG, ".jpg"),
        ("WEBP", "source.webp", "image/webp", ImageFormat.WEBP, ".webp"),
    ],
)
def test_valid_formats_are_fully_decoded_and_canonically_named(
    tmp_path: Path,
    encoded_format: str,
    filename: str,
    content_type: str,
    expected_format: ImageFormat,
    stored_suffix: str,
) -> None:
    service = make_service(tmp_path / "tasks")
    source = FakeUpload(image_bytes(encoded_format), filename, content_type)
    target = FakeUpload(image_bytes("PNG"), "private-person-name.png", "image/png")

    pair = asyncio.run(service.save_pair(TASK_ID, source, target))
    workspace_files = {path.name for path in (tmp_path / "tasks" / TASK_ID).iterdir()}

    assert pair.source.image_format is expected_format
    assert pair.source.stored_name.endswith(stored_suffix)
    assert pair.source.width == 16
    assert pair.source.height == 12
    assert workspace_files == {pair.source.stored_name, "target.png"}
    assert "private-person-name.png" not in workspace_files
    assert all(size == CHUNK_SIZE for size in source.read_sizes)


@pytest.mark.parametrize(
    ("data", "filename", "content_type", "expected_code"),
    [
        (b"not-an-image", "source.png", "image/png", "invalid_image"),
        (image_bytes("PNG"), "source.jpg", "image/jpeg", "format_mismatch"),
        (image_bytes("PNG"), "source.png", "image/jpeg", "media_type_mismatch"),
        (image_bytes("PNG"), "source.gif", "image/gif", "unsupported_extension"),
        (animated_png_bytes(), "source.png", "image/png", "animated_image"),
    ],
)
def test_invalid_images_are_rejected_and_entire_workspace_is_removed(
    tmp_path: Path,
    data: bytes,
    filename: str,
    content_type: str,
    expected_code: str,
) -> None:
    service = make_service(tmp_path / "tasks")
    valid_source = FakeUpload(image_bytes("PNG"), "source.png", "image/png")
    invalid_target = FakeUpload(data, filename, content_type)

    with pytest.raises(ImageUploadError) as captured:
        asyncio.run(service.save_pair(TASK_ID, valid_source, invalid_target))

    assert captured.value.code == expected_code
    assert not (tmp_path / "tasks" / TASK_ID).exists()


@pytest.mark.parametrize(
    ("limits", "expected_code"),
    [
        (ImageLimits(maximum_bytes=10), "file_too_large"),
        (ImageLimits(maximum_pixels=100, maximum_edge=100), "too_many_pixels"),
        (ImageLimits(maximum_pixels=1_000, maximum_edge=10), "edge_too_long"),
    ],
)
def test_byte_pixel_and_edge_limits_are_enforced(
    tmp_path: Path,
    limits: ImageLimits,
    expected_code: str,
) -> None:
    service = make_service(tmp_path / "tasks", limits)
    source = FakeUpload(image_bytes("PNG", size=(20, 20)), "source.png", "image/png")
    target = FakeUpload(image_bytes("PNG"), "target.png", "image/png")

    with pytest.raises(ImageUploadError) as captured:
        asyncio.run(service.save_pair(TASK_ID, source, target))

    assert captured.value.code == expected_code


def test_empty_upload_is_rejected(tmp_path: Path) -> None:
    service = make_service(tmp_path / "tasks")
    source = FakeUpload(b"", "source.png", "image/png")
    target = FakeUpload(image_bytes("PNG"), "target.png", "image/png")

    with pytest.raises(ImageUploadError) as captured:
        asyncio.run(service.save_pair(TASK_ID, source, target))

    assert captured.value.code == "empty_file"


def test_task_identifier_cannot_escape_workspace_root(tmp_path: Path) -> None:
    store = TaskWorkspaceStore(tmp_path / "tasks")

    with pytest.raises(ValueError, match="invalid task"):
        store.create("../outside")


def test_cancelled_upload_removes_partial_workspace(tmp_path: Path) -> None:
    service = make_service(tmp_path / "tasks")
    cancelled = CancelledUpload(image_bytes("PNG"), "source.png", "image/png")
    target = FakeUpload(image_bytes("PNG"), "target.png", "image/png")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.save_pair(TASK_ID, cancelled, target))

    assert not (tmp_path / "tasks" / TASK_ID).exists()


def test_large_valid_file_is_read_in_bounded_chunks(tmp_path: Path) -> None:
    service = make_service(tmp_path / "tasks")
    data = image_bytes("PNG", size=(512, 512), compress_level=0)
    source = FakeUpload(data, "source.png", "image/png")
    target = FakeUpload(image_bytes("PNG"), "target.png", "image/png")

    asyncio.run(service.save_pair(TASK_ID, source, target))

    assert len(source.read_sizes) > 2
    assert set(source.read_sizes) == {CHUNK_SIZE}
