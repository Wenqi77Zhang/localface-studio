"""Bounded face-swap metrics that keep identity and image fidelity distinct."""

import numpy as np
from numpy.typing import NDArray

from localface_studio.domain.faces import DetectedFace, FaceBox


def cosine_similarity(left: NDArray[np.float32], right: NDArray[np.float32]) -> float:
    """Return cosine similarity for two non-zero one-dimensional embeddings."""
    if left.ndim != 1 or right.ndim != 1 or left.shape != right.shape:
        raise ValueError("embeddings must be matching one-dimensional vectors")
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 0:
        raise ValueError("embeddings must be non-zero")
    return float(np.dot(left, right) / denominator)


def box_iou(left: FaceBox, right: FaceBox) -> float:
    """Compute intersection over union for two face boxes."""
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = left.width * left.height + right.width * right.height - intersection
    return 0.0 if union <= 0 else intersection / union


def match_output_face(
    target: DetectedFace,
    candidates: tuple[DetectedFace, ...],
    *,
    minimum_iou: float = 0.3,
) -> DetectedFace:
    """Match the post-swap face geometrically rather than by detector array order."""
    if not candidates:
        raise ValueError("output face was not detected")
    matched = max(candidates, key=lambda candidate: box_iou(target.box, candidate.box))
    if box_iou(target.box, matched.box) < minimum_iou:
        raise ValueError("output face could not be matched to the selected target")
    return matched


def landmark_nrmse(target: DetectedFace, output: DetectedFace) -> float:
    """Measure five-point displacement normalized by the target box diagonal."""
    target_points = np.asarray([(point.x, point.y) for point in target.landmarks])
    output_points = np.asarray([(point.x, point.y) for point in output.landmarks])
    diagonal = float(np.hypot(target.box.width, target.box.height))
    if diagonal <= 0:
        raise ValueError("target face diagonal must be positive")
    return float(np.sqrt(np.mean(np.sum((target_points - output_points) ** 2, axis=1))) / diagonal)


def outside_face_change_ratio(
    target: NDArray[np.uint8],
    output: NDArray[np.uint8],
    face: DetectedFace,
    *,
    pixel_threshold: int = 3,
    margin: float = 0.35,
) -> float:
    """Measure changed pixels outside a conservative expanded selected-face box."""
    if target.dtype != np.uint8 or output.dtype != np.uint8 or target.shape != output.shape:
        raise ValueError("images must be matching uint8 arrays")
    if not 0 <= pixel_threshold <= 255 or margin < 0:
        raise ValueError("metric thresholds are invalid")
    height, width = target.shape[:2]
    box = face.box
    x1 = max(0, int(np.floor(box.x - box.width * margin)))
    y1 = max(0, int(np.floor(box.y - box.height * margin)))
    x2 = min(width, int(np.ceil(box.x + box.width * (1 + margin))))
    y2 = min(height, int(np.ceil(box.y + box.height * (1 + margin))))
    outside = np.ones((height, width), dtype=bool)
    outside[y1:y2, x1:x2] = False
    if not np.any(outside):
        return 0.0
    difference = np.max(
        np.abs(output.astype(np.int16) - target.astype(np.int16)),
        axis=2,
    )
    return float(np.mean(difference[outside] > pixel_threshold))
