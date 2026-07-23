"""Pillow-based content validation for uploaded images."""

import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from localface_studio.domain.images import ImageFormat, ImageLimits, ImageUploadError

_EXTENSION_FORMATS = {
    ".png": ImageFormat.PNG,
    ".jpg": ImageFormat.JPEG,
    ".jpeg": ImageFormat.JPEG,
    ".webp": ImageFormat.WEBP,
}
_MIME_FORMATS = {
    "image/png": ImageFormat.PNG,
    "image/jpeg": ImageFormat.JPEG,
    "image/webp": ImageFormat.WEBP,
}
_PILLOW_FORMATS = {
    "PNG": ImageFormat.PNG,
    "JPEG": ImageFormat.JPEG,
    "WEBP": ImageFormat.WEBP,
}


class PillowImageValidator:
    """Validate declared type, encoded format, dimensions, frames, and decoding."""

    def __init__(self, *, limits: ImageLimits | None = None) -> None:
        self._limits = limits or ImageLimits()

    def validate(
        self,
        path: Path,
        *,
        original_filename: str | None,
        declared_content_type: str | None,
    ) -> tuple[str, int, int, str]:
        """Return canonical format facts only after a complete safe decode."""
        expected = self._expected_format(original_filename, declared_content_type)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    actual = _PILLOW_FORMATS.get(image.format or "")
                    width, height = image.size
                    mode = image.mode
                    frame_count = getattr(image, "n_frames", 1)
                    self._validate_header(actual, expected, width, height, frame_count)
                    image.verify()
                with Image.open(path) as decoded:
                    decoded.load()
        except ImageUploadError:
            raise
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            SyntaxError,
            UnidentifiedImageError,
        ) as error:
            raise ImageUploadError(
                "invalid_image",
                "The image is damaged, unsafe, or cannot be decoded.",
            ) from error
        return expected.value, width, height, mode

    def _expected_format(
        self,
        original_filename: str | None,
        declared_content_type: str | None,
    ) -> ImageFormat:
        suffix = Path(original_filename or "").suffix.casefold()
        expected = _EXTENSION_FORMATS.get(suffix)
        if expected is None:
            raise ImageUploadError(
                "unsupported_extension",
                "Use a PNG, JPEG, or static WebP file.",
            )
        declared = _MIME_FORMATS.get((declared_content_type or "").casefold())
        if declared is not expected:
            raise ImageUploadError(
                "media_type_mismatch",
                "The file extension and declared media type do not match.",
            )
        return expected

    def _validate_header(
        self,
        actual: ImageFormat | None,
        expected: ImageFormat,
        width: int,
        height: int,
        frame_count: int,
    ) -> None:
        if actual is None:
            raise ImageUploadError(
                "unsupported_format",
                "The decoded image format is not supported.",
            )
        if actual is not expected:
            raise ImageUploadError(
                "format_mismatch",
                "The file extension does not match the encoded image format.",
            )
        if frame_count != 1:
            raise ImageUploadError(
                "animated_image",
                "Animated or multi-frame images are not supported.",
            )
        if width * height > self._limits.maximum_pixels:
            raise ImageUploadError(
                "too_many_pixels",
                "The image exceeds the 50 million pixel limit.",
            )
        if max(width, height) > self._limits.maximum_edge:
            raise ImageUploadError(
                "edge_too_long",
                "The image longest edge exceeds 12000 pixels.",
            )
