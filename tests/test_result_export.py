"""Privacy-safe result metadata and atomic export helpers."""

from pathlib import Path

import pytest
from PIL import Image

from localface_studio.backends.result_export import save_result
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
