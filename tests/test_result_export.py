"""Privacy-safe result metadata and atomic export helpers."""

from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont

from localface_studio.backends import result_export
from localface_studio.backends.result_export import AI_WATERMARK, draw_ai_watermark, save_result
from localface_studio.domain.tasks import OutputFormat


def safe_metadata() -> dict[str, object]:
    return {
        "app": "LocalFace Studio",
        "app_version": "test",
        "ai_edited": True,
        "backend": "test",
        "created_at": "2026-08-26T00:00:00+00:00",
        "simulation": False,
        "visible_watermark": True,
    }


def test_export_rejects_unknown_or_incomplete_metadata(tmp_path: Path) -> None:
    image = Image.new("RGB", (8, 8))
    destination = tmp_path / "result.png"
    with pytest.raises(ValueError, match="privacy-safe schema"):
        save_result(
            image,
            destination,
            OutputFormat.PNG,
            {**safe_metadata(), "actor_id": "private"},
            jpeg_quality=95,
        )
    assert not destination.exists()

    incomplete = safe_metadata()
    incomplete.pop("ai_edited")
    with pytest.raises(ValueError, match="privacy-safe schema"):
        save_result(
            image,
            destination,
            OutputFormat.PNG,
            incomplete,
            jpeg_quality=95,
        )
    assert not destination.exists()


def test_watermark_respects_glyph_bearing_and_bottom_padding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    font = ImageFont.load_default(size=28)
    monkeypatch.setattr(result_export, "_load_font", lambda _size: font)
    image = Image.new("RGB", (1536, 1024), "black")
    draw_ai_watermark(image)
    glyph_bounds = ImageChops.difference(image, Image.new("RGB", image.size, "black")).getbbox()
    assert glyph_bounds is not None
    font_bounds = ImageDraw.Draw(image).textbbox((0, 0), AI_WATERMARK, font=font)
    padding = 28 // 3
    assert glyph_bounds[3] <= image.height - padding
    assert glyph_bounds[2] <= image.width - padding
    assert glyph_bounds[3] - glyph_bounds[1] == font_bounds[3] - font_bounds[1]
