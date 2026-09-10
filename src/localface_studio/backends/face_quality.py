"""Deterministic, model-free post-processing presets for a selected face."""

from dataclasses import replace

import cv2
import numpy as np
from numpy.typing import NDArray

from localface_studio.domain.faces import DetectedFace


class ColorHarmonizationEnhancer:
    """Conservative colour correction, explicitly not generative face restoration."""

    enhancer_id = "local-color-harmonization-v2"

    def enhance(
        self,
        target: NDArray[np.uint8],
        base: NDArray[np.uint8],
        target_face: DetectedFace,
    ) -> NDArray[np.uint8]:
        return harmonize_face_color(target, base, target_face)


def harmonize_face_color(
    target: NDArray[np.uint8],
    swapped: NDArray[np.uint8],
    face: DetectedFace,
    *,
    strength: float = 0.35,
) -> NDArray[np.uint8]:
    """Gently match face colour while preserving the model-generated core pixels."""
    if target.dtype != np.uint8 or swapped.dtype != np.uint8:
        raise ValueError("quality inputs must be uint8 images")
    if target.shape != swapped.shape or target.ndim != 3 or target.shape[2] != 3:
        raise ValueError("quality inputs must have matching BGR shapes")
    if not 0 <= strength <= 1:
        raise ValueError("quality strength must be between zero and one")
    if strength == 0:
        return swapped.copy()

    height, width = target.shape[:2]
    # Work on a bounded face ROI, not multiple floating-point copies of a 24 MP photo.
    box = face.box
    pad = max(box.width, box.height) * 0.3 + 4
    x0, y0 = max(0, int(box.x - pad)), max(0, int(box.y - pad))
    x1 = min(width, int(np.ceil(box.x + box.width + pad)))
    y1 = min(height, int(np.ceil(box.y + box.height + pad)))
    if x1 <= x0 or y1 <= y0:
        return swapped.copy()
    local_face = replace(face, box=replace(box, x=box.x - x0, y=box.y - y0))
    mask = face_blend_mask(x1 - x0, y1 - y0, local_face)
    core = mask >= 0.8
    if np.count_nonzero(core) < 16:
        return swapped.copy()

    target_lab = cv2.cvtColor(target[y0:y1, x0:x1], cv2.COLOR_BGR2LAB).astype(np.float32)
    swapped_lab = cv2.cvtColor(swapped[y0:y1, x0:x1], cv2.COLOR_BGR2LAB).astype(np.float32)
    target_center = np.median(target_lab[core], axis=0)
    swapped_center = np.median(swapped_lab[core], axis=0)
    shift = np.clip(target_center - swapped_center, (-10, -6, -6), (10, 6, 6))
    blend = (mask * strength)[:, :, None]
    harmonized_lab = swapped_lab + shift[None, None, :] * blend
    harmonized_lab = np.clip(harmonized_lab, 0, 255).astype(np.uint8)
    converted = cv2.cvtColor(harmonized_lab, cv2.COLOR_LAB2BGR)
    result = swapped.copy()
    # Do not colour untouched background or neighbouring faces merely inside an ellipse.
    changed = np.any(target[y0:y1, x0:x1] != swapped[y0:y1, x0:x1], axis=2)
    active = (mask >= 0.001) & changed
    result[y0:y1, x0:x1][active] = converted[active]
    return result


def face_blend_mask(
    width: int,
    height: int,
    face: DetectedFace,
) -> NDArray[np.float32]:
    """Build the bounded feather mask shared by optimization and evaluation."""
    if width < 1 or height < 1:
        raise ValueError("mask dimensions must be positive")
    box = face.box
    center = (
        round(np.clip(box.x + box.width * 0.5, 0, width - 1)),
        round(np.clip(box.y + box.height * 0.52, 0, height - 1)),
    )
    axes = (
        max(1, round(min(box.width * 0.43, width / 2))),
        max(1, round(min(box.height * 0.48, height / 2))),
    )
    mask = np.zeros((height, width), dtype=np.float32)
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, thickness=-1)
    sigma = max(1.0, min(box.width, box.height) * 0.055)
    return np.asarray(
        cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma),
        dtype=np.float32,
    )
