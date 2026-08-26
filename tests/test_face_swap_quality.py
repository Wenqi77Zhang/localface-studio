"""Face-swap metric contract tests using synthetic geometry and pixels."""

import numpy as np
import pytest

from localface_studio.benchmarking.face_swap_quality import (
    box_iou,
    cosine_similarity,
    landmark_nrmse,
    match_output_face,
    outside_face_change_ratio,
)
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    stable_detection_id,
)


def _face(x: float, y: float = 10) -> DetectedFace:
    box = FaceBox(x=x, y=y, width=20, height=24)
    landmarks = tuple(FacePoint(x=x + 5 + index * 2, y=y + 8 + index) for index in range(5))
    return DetectedFace(
        detection_id=stable_detection_id("test", box, landmarks),
        detector_id="test",
        box=box,
        landmarks=landmarks,
        confidence=0.99,
    )


def test_identity_and_geometry_metrics_are_bounded() -> None:
    first = np.asarray([1, 0, 0], dtype=np.float32)
    second = np.asarray([0.8, 0.6, 0], dtype=np.float32)
    assert cosine_similarity(first, first) == pytest.approx(1)
    assert cosine_similarity(first, second) == pytest.approx(0.8)
    assert box_iou(_face(10).box, _face(10).box) == pytest.approx(1)
    assert landmark_nrmse(_face(10), _face(10)) == pytest.approx(0)
    assert match_output_face(_face(10), (_face(50), _face(11))).box.x == 11


def test_outside_metric_ignores_selected_region_but_detects_background_change() -> None:
    target = np.zeros((64, 80, 3), dtype=np.uint8)
    output = target.copy()
    output[10:34, 10:30] = 200
    assert outside_face_change_ratio(target, output, _face(10)) == 0
    output[0, 0] = 200
    assert outside_face_change_ratio(target, output, _face(10)) > 0


def test_metric_invalid_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="matching"):
        cosine_similarity(np.ones(2, dtype=np.float32), np.ones(3, dtype=np.float32))
    with pytest.raises(ValueError, match="non-zero"):
        cosine_similarity(np.zeros(2, dtype=np.float32), np.ones(2, dtype=np.float32))
    with pytest.raises(ValueError, match="not detected"):
        match_output_face(_face(10), ())
    with pytest.raises(ValueError, match="matching uint8"):
        outside_face_change_ratio(
            np.zeros((2, 2, 3), dtype=np.uint8),
            np.zeros((3, 2, 3), dtype=np.uint8),
            _face(10),
        )
