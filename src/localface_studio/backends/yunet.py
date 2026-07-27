"""OpenCV YuNet adapter with integrity checks and deterministic face IDs."""

from pathlib import Path
from threading import Lock
from typing import Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from localface_studio.application.face_detection import FaceImage
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    face_display_order,
    stable_detection_id,
)
from localface_studio.infrastructure.model_manifest import (
    ModelManifestError,
    load_model_artifact,
    verify_model_artifact,
)

YUNET_MODEL_ID = "yunet-opencv"


class FaceDetectionError(RuntimeError):
    """Expected detector failure with a stable non-sensitive error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _YuNetEngine(Protocol):
    def setInputSize(self, input_size: tuple[int, int]) -> None:
        """Set width and height for the next inference."""
        ...

    def detect(
        self,
        image: FaceImage,
    ) -> tuple[int, NDArray[np.float32] | None]:
        """Return OpenCV status and rows of boxes, landmarks, and confidence."""
        ...


class YuNetFaceDetector:
    """CPU-first YuNet detector that returns original-image coordinates."""

    def __init__(
        self,
        model_path: Path,
        *,
        score_threshold: float = 0.9,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        maximum_input_edge: int = 1920,
    ) -> None:
        if not 0 < score_threshold <= 1:
            raise ValueError("score_threshold must be greater than zero and at most one")
        if not 0 < nms_threshold <= 1:
            raise ValueError("nms_threshold must be greater than zero and at most one")
        if top_k < 1 or maximum_input_edge < 32:
            raise ValueError("top_k and maximum_input_edge are outside supported bounds")
        try:
            engine = _create_yunet_engine(
                model_path,
                score_threshold=score_threshold,
                nms_threshold=nms_threshold,
                top_k=top_k,
            )
        except cv2.error as error:
            raise FaceDetectionError("face_detector_load_failed") from error
        self._engine = engine
        self._maximum_input_edge = maximum_input_edge
        self._lock = Lock()

    @classmethod
    def from_manifest(
        cls,
        manifest_path: Path,
        project_root: Path,
        *,
        commercial_mode: bool = False,
        score_threshold: float = 0.9,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        maximum_input_edge: int = 1920,
    ) -> YuNetFaceDetector:
        """Load only a verified and license-compatible YuNet artifact."""
        artifact = load_model_artifact(manifest_path, YUNET_MODEL_ID)
        if artifact.role != "face_detector":
            raise ModelManifestError("model_role_mismatch")
        if commercial_mode and not artifact.commercial_mode_allowed:
            raise ModelManifestError("model_not_allowed_in_commercial_mode")
        model_path = verify_model_artifact(artifact, project_root)
        return cls(
            model_path,
            score_threshold=score_threshold,
            nms_threshold=nms_threshold,
            top_k=top_k,
            maximum_input_edge=maximum_input_edge,
        )

    @property
    def detector_id(self) -> str:
        return YUNET_MODEL_ID

    def detect(self, image: FaceImage) -> tuple[DetectedFace, ...]:
        """Run YuNet without retaining pixels or detector output after return."""
        height, width = _validate_image(image)
        inference_image, scale = _prepare_inference_image(
            image,
            maximum_input_edge=self._maximum_input_edge,
        )
        inference_height, inference_width = inference_image.shape[:2]
        try:
            with self._lock:
                self._engine.setInputSize((inference_width, inference_height))
                status, rows = self._engine.detect(inference_image)
        except cv2.error as error:
            raise FaceDetectionError("face_detection_inference_failed") from error
        if status == 0:
            raise FaceDetectionError("face_detection_inference_failed")
        if rows is None:
            return ()
        faces_by_id: dict[str, DetectedFace] = {}
        for row in np.asarray(rows):
            face = _parse_row(row, original_width=width, original_height=height, scale=scale)
            existing = faces_by_id.get(face.detection_id)
            if existing is None or face.confidence > existing.confidence:
                faces_by_id[face.detection_id] = face
        return tuple(sorted(faces_by_id.values(), key=face_display_order))


def _validate_image(image: FaceImage) -> tuple[int, int]:
    if not isinstance(image, np.ndarray):
        raise FaceDetectionError("face_detection_image_invalid")
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise FaceDetectionError("face_detection_image_invalid")
    height, width = image.shape[:2]
    if height < 1 or width < 1:
        raise FaceDetectionError("face_detection_image_invalid")
    return height, width


def _prepare_inference_image(
    image: FaceImage,
    *,
    maximum_input_edge: int,
) -> tuple[FaceImage, float]:
    height, width = image.shape[:2]
    scale = min(1.0, maximum_input_edge / max(height, width))
    if scale == 1:
        return np.ascontiguousarray(image), scale
    resized = cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(resized), scale


def _parse_row(
    row: NDArray[np.generic],
    *,
    original_width: int,
    original_height: int,
    scale: float,
) -> DetectedFace:
    flattened = np.asarray(row, dtype=np.float64).reshape(-1)
    if flattened.size < 15 or not np.isfinite(flattened[:15]).all():
        raise FaceDetectionError("face_detection_output_invalid")
    x, y, width, height = (float(value) / scale for value in flattened[:4])
    x1 = min(float(original_width), max(0.0, x))
    y1 = min(float(original_height), max(0.0, y))
    x2 = min(float(original_width), max(0.0, x + width))
    y2 = min(float(original_height), max(0.0, y + height))
    if x2 <= x1 or y2 <= y1:
        raise FaceDetectionError("face_detection_output_invalid")
    box = FaceBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1)
    landmark_values = flattened[4:14].reshape(5, 2) / scale
    landmarks = tuple(
        FacePoint(
            x=min(float(original_width - 1), max(0.0, float(point[0]))),
            y=min(float(original_height - 1), max(0.0, float(point[1]))),
        )
        for point in landmark_values
    )
    confidence = float(flattened[14])
    if not 0 <= confidence <= 1:
        raise FaceDetectionError("face_detection_output_invalid")
    return DetectedFace(
        detection_id=stable_detection_id(YUNET_MODEL_ID, box, landmarks),
        detector_id=YUNET_MODEL_ID,
        box=box,
        landmarks=landmarks,
        confidence=confidence,
    )


def _create_yunet_engine(
    model_path: Path,
    *,
    score_threshold: float,
    nms_threshold: float,
    top_k: int,
) -> _YuNetEngine:
    engine = cv2.FaceDetectorYN.create(
        str(model_path),
        "",
        (320, 320),
        score_threshold,
        nms_threshold,
        top_k,
    )
    return cast(_YuNetEngine, engine)
