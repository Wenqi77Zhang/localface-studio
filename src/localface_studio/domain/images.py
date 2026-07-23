"""Image-upload contracts without user filenames or filesystem paths."""

from dataclasses import dataclass
from enum import StrEnum


class ImageRole(StrEnum):
    """Fixed image roles used as canonical storage names."""

    SOURCE = "source"
    TARGET = "target"


class ImageFormat(StrEnum):
    """Input formats accepted by the frozen phase 2 plan."""

    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"


@dataclass(frozen=True, slots=True)
class ImageLimits:
    """Hard limits checked before a decoded image can enter a task."""

    maximum_bytes: int = 25 * 1024 * 1024
    maximum_pixels: int = 50_000_000
    maximum_edge: int = 12_000

    def __post_init__(self) -> None:
        if min(self.maximum_bytes, self.maximum_pixels, self.maximum_edge) < 1:
            raise ValueError("image limits must be positive")


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    """Privacy-safe image facts returned after full decoding."""

    role: ImageRole
    image_format: ImageFormat
    width: int
    height: int
    mode: str
    byte_count: int
    stored_name: str


@dataclass(frozen=True, slots=True)
class UploadedImagePair:
    """Validated source and target images stored in one isolated workspace."""

    task_id: str
    source: ValidatedImage
    target: ValidatedImage


class ImageUploadError(ValueError):
    """User-correctable upload rejection with a stable public error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
