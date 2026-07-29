"""Image decoding helpers shared by product and benchmark paths."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def decode_bgr_autorotated(path: Path) -> np.ndarray:
    """Decode one image to contiguous BGR pixels after applying EXIF orientation."""
    with Image.open(path) as image:
        upright = ImageOps.exif_transpose(image)
        rgb = np.asarray(upright.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])
