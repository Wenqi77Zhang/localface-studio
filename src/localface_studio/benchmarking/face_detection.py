"""Deterministic face-detection benchmark contracts and IoU evaluation."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from localface_studio.domain.faces import DetectedFace, FaceBox

BENCHMARK_SCHEMA_VERSION = 1


class BenchmarkManifestError(ValueError):
    """Raised when a benchmark manifest is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class NormalizedBox:
    """Ground-truth box in normalized zero-to-one coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(type(value) in (int, float) for value in values):
            raise BenchmarkManifestError("ground-truth box values must be numbers")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise BenchmarkManifestError("ground-truth box values are outside bounds")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise BenchmarkManifestError("ground-truth box must stay inside the image")


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One licensed or synthetic image and its manually reviewed truth."""

    case_id: str
    image_path: PurePosixPath
    categories: tuple[str, ...]
    faces: tuple[NormalizedBox, ...]
    provenance: str


@dataclass(frozen=True, slots=True)
class BenchmarkManifest:
    """Versioned evaluation set independent of a detector implementation."""

    detector_id: str
    cases: tuple[BenchmarkCase, ...]


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case_id: str
    expected_faces: int
    detected_faces: int
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def recall(self) -> float:
        return (
            self.true_positives / self.expected_faces
            if self.expected_faces > 0
            else float(self.false_positives == 0)
        )

    @property
    def precision(self) -> float:
        return (
            self.true_positives / self.detected_faces
            if self.detected_faces > 0
            else float(self.expected_faces == 0)
        )


def load_benchmark_manifest(path: Path) -> BenchmarkManifest:
    """Load a strict JSON manifest without accepting absolute or escaping paths."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BenchmarkManifestError("benchmark_manifest_unreadable") from error
    root = _object(payload, "benchmark manifest")
    if set(root) != {"schema_version", "detector_id", "cases"}:
        raise BenchmarkManifestError("benchmark manifest fields are invalid")
    if root["schema_version"] != BENCHMARK_SCHEMA_VERSION:
        raise BenchmarkManifestError("benchmark schema version is unsupported")
    detector_id = _nonempty_text(root["detector_id"], "detector_id")
    raw_cases = root["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkManifestError("benchmark cases must be a non-empty array")
    cases = tuple(_parse_case(value) for value in raw_cases)
    identifiers = [case.case_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise BenchmarkManifestError("benchmark case IDs must be unique")
    return BenchmarkManifest(detector_id=detector_id, cases=cases)


def evaluate_case(
    case: BenchmarkCase,
    detections: tuple[DetectedFace, ...],
    *,
    image_width: int,
    image_height: int,
    iou_threshold: float = 0.5,
) -> CaseEvaluation:
    """Match detections to truth once each using descending IoU."""
    if image_width < 1 or image_height < 1:
        raise ValueError("image dimensions must be positive")
    if not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be greater than zero and at most one")
    predicted = tuple(
        _normalize_box(face.box, image_width=image_width, image_height=image_height)
        for face in detections
    )
    candidates = sorted(
        (
            (_iou(expected, actual), expected_index, actual_index)
            for expected_index, expected in enumerate(case.faces)
            for actual_index, actual in enumerate(predicted)
        ),
        reverse=True,
    )
    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    for overlap, expected_index, actual_index in candidates:
        if overlap < iou_threshold:
            break
        if expected_index in matched_expected or actual_index in matched_actual:
            continue
        matched_expected.add(expected_index)
        matched_actual.add(actual_index)
    true_positives = len(matched_expected)
    return CaseEvaluation(
        case_id=case.case_id,
        expected_faces=len(case.faces),
        detected_faces=len(predicted),
        true_positives=true_positives,
        false_positives=len(predicted) - true_positives,
        false_negatives=len(case.faces) - true_positives,
    )


def _parse_case(value: Any) -> BenchmarkCase:
    raw = _object(value, "benchmark case")
    if set(raw) != {"id", "image", "categories", "faces", "provenance"}:
        raise BenchmarkManifestError("benchmark case fields are invalid")
    case_id = _nonempty_text(raw["id"], "case id")
    image_path = _relative_path(raw["image"])
    categories = raw["categories"]
    if (
        not isinstance(categories, list)
        or not categories
        or not all(isinstance(category, str) and category.strip() for category in categories)
    ):
        raise BenchmarkManifestError("benchmark categories are invalid")
    raw_faces = raw["faces"]
    if not isinstance(raw_faces, list):
        raise BenchmarkManifestError("benchmark faces must be an array")
    faces = tuple(_parse_box(face) for face in raw_faces)
    return BenchmarkCase(
        case_id=case_id,
        image_path=image_path,
        categories=tuple(categories),
        faces=faces,
        provenance=_nonempty_text(raw["provenance"], "provenance"),
    )


def _parse_box(value: Any) -> NormalizedBox:
    raw = _object(value, "ground-truth box")
    if set(raw) != {"x", "y", "width", "height"}:
        raise BenchmarkManifestError("ground-truth box fields are invalid")
    return NormalizedBox(
        x=raw["x"],
        y=raw["y"],
        width=raw["width"],
        height=raw["height"],
    )


def _relative_path(value: Any) -> PurePosixPath:
    text = _nonempty_text(value, "image path")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text:
        raise BenchmarkManifestError("benchmark image path must be safe and relative")
    return path


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise BenchmarkManifestError(f"{label} must be an object")
    return value


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkManifestError(f"{label} must be non-empty text")
    return value


def _normalize_box(box: FaceBox, *, image_width: int, image_height: int) -> NormalizedBox:
    return NormalizedBox(
        x=box.x / image_width,
        y=box.y / image_height,
        width=box.width / image_width,
        height=box.height / image_height,
    )


def _iou(first: NormalizedBox, second: NormalizedBox) -> float:
    left = max(first.x, second.x)
    top = max(first.y, second.y)
    right = min(first.x + first.width, second.x + second.width)
    bottom = min(first.y + first.height, second.y + second.height)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union > 0 else 0.0
