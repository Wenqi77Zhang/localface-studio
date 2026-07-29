"""Generated-image tests for shared EXIF-aware decoding."""

from pathlib import Path

from PIL import Image

from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated


def test_decode_applies_exif_orientation_before_bgr_conversion(tmp_path: Path) -> None:
    path = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (6, 4), color=(240, 10, 20))
    image.getexif()[274] = 6
    image.save(path, format="JPEG", exif=image.getexif(), quality=100, subsampling=0)

    decoded = decode_bgr_autorotated(path)

    assert decoded.shape == (6, 4, 3)
    assert decoded.flags.c_contiguous
    assert decoded[0, 0].tolist() == [20, 10, 240]


def test_decode_preserves_unoriented_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "plain.png"
    Image.new("RGB", (7, 5), color=(30, 60, 90)).save(path, format="PNG")

    decoded = decode_bgr_autorotated(path)

    assert decoded.shape == (5, 7, 3)
    assert decoded[0, 0].tolist() == [90, 60, 30]
