"""Shared, atomic image export with durable AI-edit disclosure metadata."""

import json
import os
from collections.abc import Iterable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from localface_studio.domain.tasks import OutputFormat

AI_WATERMARK = "AI EDITED - LocalFace Studio"
METADATA_KEY = "LocalFaceStudio"
SAFE_METADATA_KEYS = frozenset(
    {
        "ai_edited",
        "app",
        "app_version",
        "backend",
        "created_at",
        "detector_id",
        "execution_providers",
        "jpeg_quality",
        "quality_preset",
        "simulation",
        "statement",
        "swap_model_id",
        "visible_watermark",
    }
)
REQUIRED_METADATA_KEYS = frozenset(
    {"ai_edited", "app", "app_version", "backend", "created_at", "simulation", "visible_watermark"}
)


def draw_ai_watermark(image: Image.Image) -> None:
    """Draw a compact visible disclosure without changing the canvas size."""
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    font_size = max(12, min(28, width // 26, height // 12))
    font = _load_font(font_size)
    padding = max(5, font_size // 3)
    box = draw.textbbox((0, 0), AI_WATERMARK, font=font)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    left = max(0, width - text_width - 2 * padding)
    top = max(0, height - text_height - 2 * padding)
    draw.rounded_rectangle(
        (left, top, width, height),
        radius=max(4, padding),
        fill=(0, 0, 0, 180),
    )
    draw.text((left + padding, top + padding), AI_WATERMARK, font=font, fill=(255, 255, 255, 240))


def save_result(
    image: Image.Image,
    destination: Path,
    output_format: OutputFormat,
    metadata: dict[str, object],
    *,
    jpeg_quality: int,
) -> None:
    """Encode a result with metadata in PNG text or JPEG EXIF."""
    _validate_metadata(metadata)
    if output_format is OutputFormat.PNG:
        serialized = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text(METADATA_KEY, serialized)
        image.save(destination, format="PNG", pnginfo=png_info)
        return
    serialized = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
    exif = Image.Exif()
    exif[270] = serialized
    exif[305] = "LocalFace Studio"
    image.convert("RGB").save(destination, format="JPEG", quality=jpeg_quality, exif=exif)


def read_result_metadata(image: Image.Image, output_format: OutputFormat) -> dict[str, object]:
    """Read and structurally validate LocalFace Studio result metadata."""
    raw = (
        image.info.get(METADATA_KEY)
        if output_format is OutputFormat.PNG
        else image.getexif().get(270)
    )
    if not isinstance(raw, str):
        raise ValueError("result metadata is absent")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("result metadata is not an object")
    return value


def _validate_metadata(metadata: dict[str, object]) -> None:
    unknown = metadata.keys() - SAFE_METADATA_KEYS
    missing = REQUIRED_METADATA_KEYS - metadata.keys()
    if unknown or missing:
        raise ValueError("result metadata does not match the privacy-safe schema")
    if metadata.get("ai_edited") is not True or metadata.get("app") != "LocalFace Studio":
        raise ValueError("result metadata disclosure is invalid")


def _font_candidates() -> Iterable[Path]:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    yield windows / "segoeui.ttf"
    yield windows / "arial.ttf"
    yield Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _font_candidates():
        if candidate.is_file():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)
