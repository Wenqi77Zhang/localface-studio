"""Deterministic quality-preset regression tests."""

import cv2
import numpy as np
import pytest

from localface_studio.backends.face_quality import face_blend_mask, harmonize_face_color
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    stable_detection_id,
)


def _face() -> DetectedFace:
    box = FaceBox(x=20, y=12, width=24, height=28)
    landmarks = tuple(FacePoint(x=26 + index * 3, y=20 + index) for index in range(5))
    return DetectedFace(
        detection_id=stable_detection_id("test", box, landmarks),
        detector_id="test",
        box=box,
        landmarks=landmarks,
        confidence=0.99,
    )


def test_balanced_harmonization_moves_face_colour_toward_target_only_locally() -> None:
    target = np.full((56, 72, 3), (80, 105, 130), dtype=np.uint8)
    swapped = np.full((56, 72, 3), (50, 75, 100), dtype=np.uint8)
    result = harmonize_face_color(target, swapped, _face())

    target_lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB)
    swapped_lab = cv2.cvtColor(swapped, cv2.COLOR_BGR2LAB)
    result_lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
    center = (28, 32)
    assert np.linalg.norm(
        result_lab[center].astype(float) - target_lab[center].astype(float)
    ) < np.linalg.norm(swapped_lab[center].astype(float) - target_lab[center].astype(float))
    assert np.array_equal(result[:5, :5], swapped[:5, :5])
    assert np.max(np.abs(result.astype(int) - swapped.astype(int))) <= 11


def test_zero_strength_is_exact_identity_and_invalid_inputs_fail() -> None:
    image = np.full((56, 72, 3), 80, dtype=np.uint8)
    assert np.array_equal(harmonize_face_color(image, image, _face(), strength=0), image)
    with pytest.raises(ValueError, match="matching BGR"):
        harmonize_face_color(image, image[:, :-1], _face())
    with pytest.raises(ValueError, match="between zero and one"):
        harmonize_face_color(image, image, _face(), strength=1.1)
    with pytest.raises(ValueError, match="dimensions"):
        face_blend_mask(0, 10, _face())
