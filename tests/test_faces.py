"""Pure face detection value and stable identifier tests."""

import pytest

from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    face_display_order,
    stable_detection_id,
)


def landmarks(offset: float = 0) -> tuple[FacePoint, ...]:
    return tuple(FacePoint(offset + value, offset + value) for value in range(5))


def test_stable_detection_id_depends_on_geometry_not_array_order() -> None:
    box = FaceBox(10, 20, 30, 40)
    points = landmarks()

    first = stable_detection_id("yunet-opencv", box, points)
    second = stable_detection_id("yunet-opencv", box, points)
    moved = stable_detection_id("yunet-opencv", FaceBox(11, 20, 30, 40), points)

    assert first == second
    assert first != moved
    assert first.startswith("face_")
    assert len(first) == 25


def test_display_order_is_geometric_and_face_contract_rejects_invalid_values() -> None:
    points = landmarks()
    upper = DetectedFace(
        stable_detection_id("yunet-opencv", FaceBox(80, 10, 20, 20), points),
        "yunet-opencv",
        FaceBox(80, 10, 20, 20),
        points,
        0.95,
    )
    lower = DetectedFace(
        stable_detection_id("yunet-opencv", FaceBox(10, 50, 20, 20), points),
        "yunet-opencv",
        FaceBox(10, 50, 20, 20),
        points,
        0.9,
    )

    assert sorted((lower, upper), key=face_display_order) == [upper, lower]
    with pytest.raises(ValueError, match="five landmarks"):
        DetectedFace("face_" + "0" * 20, "yunet-opencv", upper.box, points[:4], 0.9)
    with pytest.raises(ValueError, match="between zero and one"):
        DetectedFace("face_" + "0" * 20, "yunet-opencv", upper.box, points, 1.1)


def test_face_geometry_rejects_non_finite_negative_and_empty_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        FacePoint(float("nan"), 0)
    with pytest.raises(ValueError, match="negative"):
        FacePoint(-1, 0)
    with pytest.raises(ValueError, match="positive"):
        FaceBox(0, 0, 0, 10)
    with pytest.raises(ValueError, match="blank"):
        stable_detection_id("", FaceBox(0, 0, 10, 10), landmarks())
    with pytest.raises(ValueError, match="five landmarks"):
        stable_detection_id("yunet-opencv", FaceBox(0, 0, 10, 10), landmarks()[:4])
