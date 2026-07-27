"""Privacy-safe face detection values shared by detectors and selection flows."""

from dataclasses import dataclass
from hashlib import blake2s
from math import isfinite


@dataclass(frozen=True, slots=True)
class FacePoint:
    """One landmark in original-image pixel coordinates."""

    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise ValueError("face point coordinates must be finite")
        if self.x < 0 or self.y < 0:
            raise ValueError("face point coordinates must not be negative")


@dataclass(frozen=True, slots=True)
class FaceBox:
    """A face boundary in original-image pixel coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x, self.y, self.width, self.height)):
            raise ValueError("face box values must be finite")
        if self.x < 0 or self.y < 0:
            raise ValueError("face box origin must not be negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("face box dimensions must be positive")


@dataclass(frozen=True, slots=True)
class DetectedFace:
    """One detector result without embeddings, image bytes, or local paths."""

    detection_id: str
    detector_id: str
    box: FaceBox
    landmarks: tuple[FacePoint, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not self.detection_id.startswith("face_") or len(self.detection_id) != 25:
            raise ValueError("detection_id must be a stable face digest")
        if not self.detector_id.strip():
            raise ValueError("detector_id must not be blank")
        if len(self.landmarks) != 5:
            raise ValueError("exactly five landmarks are required")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")


def stable_detection_id(
    detector_id: str,
    box: FaceBox,
    landmarks: tuple[FacePoint, ...],
) -> str:
    """Derive an order-independent ID from detector identity and face geometry."""
    if not detector_id.strip():
        raise ValueError("detector_id must not be blank")
    if len(landmarks) != 5:
        raise ValueError("exactly five landmarks are required")
    values = (
        box.x,
        box.y,
        box.width,
        box.height,
        *(coordinate for point in landmarks for coordinate in (point.x, point.y)),
    )
    canonical = "|".join((detector_id, *(f"{value:.3f}" for value in values)))
    digest = blake2s(canonical.encode("utf-8"), digest_size=10).hexdigest()
    return f"face_{digest}"


def face_display_order(face: DetectedFace) -> tuple[float, float, float, float, str]:
    """Sort faces top-to-bottom then left-to-right without using detector array order."""
    return (
        round(face.box.y, 3),
        round(face.box.x, 3),
        round(face.box.height, 3),
        round(face.box.width, 3),
        face.detection_id,
    )
