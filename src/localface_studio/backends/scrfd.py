"""Research-only InsightFace SCRFD adapter without bundled model weights."""

from pathlib import Path
from threading import Lock
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from localface_studio.application.face_detection import FaceImage
from localface_studio.backends.face_detection_common import (
    FaceDetectionError,
    validate_face_image,
)
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

SCRFD_RESEARCH_MODEL_ID = "scrfd-insightface-research"


class _ScrfdEngine(Protocol):
    def detect(
        self,
        image: FaceImage,
        input_size: None = None,
        max_num: int = 0,
    ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
        """Return boxes shaped N x 5 and optional landmarks shaped N x 5 x 2."""
        ...


class ScrfdResearchFaceDetector:
    """CPU-only SCRFD detector guarded by explicit research-license acceptance."""

    def __init__(
        self,
        model_path: Path,
        *,
        commercial_mode: bool = False,
        research_license_accepted: bool = False,
        score_threshold: float = 0.5,
        nms_threshold: float = 0.4,
        input_sizes: tuple[tuple[int, int], ...] = ((128, 128), (640, 640)),
    ) -> None:
        if commercial_mode:
            raise ModelManifestError("model_not_allowed_in_commercial_mode")
        if research_license_accepted is not True:
            raise ModelManifestError("model_license_not_accepted")
        if not 0 < score_threshold <= 1:
            raise ValueError("score_threshold must be greater than zero and at most one")
        if not 0 < nms_threshold <= 1:
            raise ValueError("nms_threshold must be greater than zero and at most one")
        if not input_sizes or any(width < 32 or height < 32 for width, height in input_sizes):
            raise ValueError("input_sizes are outside supported bounds")
        self._engine = _create_scrfd_engine(
            model_path,
            score_threshold=score_threshold,
            nms_threshold=nms_threshold,
            input_sizes=input_sizes,
        )
        self._lock = Lock()

    @classmethod
    def from_manifest(
        cls,
        manifest_path: Path,
        project_root: Path,
        *,
        commercial_mode: bool = False,
        research_license_accepted: bool = False,
        score_threshold: float = 0.5,
        nms_threshold: float = 0.4,
        input_sizes: tuple[tuple[int, int], ...] = ((128, 128), (640, 640)),
    ) -> ScrfdResearchFaceDetector:
        """Load a verified SCRFD weight only after explicit license acceptance."""
        artifact = load_model_artifact(manifest_path, SCRFD_RESEARCH_MODEL_ID)
        if artifact.role != "face_detector":
            raise ModelManifestError("model_role_mismatch")
        if commercial_mode:
            raise ModelManifestError("model_not_allowed_in_commercial_mode")
        if not research_license_accepted:
            raise ModelManifestError("model_license_not_accepted")
        model_path = verify_model_artifact(artifact, project_root)
        return cls(
            model_path,
            commercial_mode=commercial_mode,
            research_license_accepted=research_license_accepted,
            score_threshold=score_threshold,
            nms_threshold=nms_threshold,
            input_sizes=input_sizes,
        )

    @property
    def detector_id(self) -> str:
        return SCRFD_RESEARCH_MODEL_ID

    def detect(self, image: FaceImage) -> tuple[DetectedFace, ...]:
        """Run SCRFD locally without retaining pixels after the call returns."""
        height, width = validate_face_image(image)
        try:
            with self._lock:
                boxes, keypoints = self._engine.detect(image, input_size=None, max_num=0)
        except Exception as error:
            raise FaceDetectionError("face_detection_inference_failed") from error
        return _parse_output(boxes, keypoints, image_width=width, image_height=height)


def _parse_output(
    boxes: NDArray[np.float32],
    keypoints: NDArray[np.float32] | None,
    *,
    image_width: int,
    image_height: int,
) -> tuple[DetectedFace, ...]:
    box_values = np.asarray(boxes, dtype=np.float64)
    if box_values.size == 0:
        return ()
    if box_values.ndim != 2 or box_values.shape[1] < 5:
        raise FaceDetectionError("face_detection_output_invalid")
    if keypoints is None:
        raise FaceDetectionError("face_detection_landmarks_missing")
    landmark_values = np.asarray(keypoints, dtype=np.float64)
    if landmark_values.shape != (box_values.shape[0], 5, 2):
        raise FaceDetectionError("face_detection_output_invalid")
    if not np.isfinite(box_values[:, :5]).all() or not np.isfinite(landmark_values).all():
        raise FaceDetectionError("face_detection_output_invalid")

    faces_by_id: dict[str, DetectedFace] = {}
    for raw_box, raw_landmarks in zip(box_values, landmark_values, strict=True):
        x1 = min(float(image_width), max(0.0, float(raw_box[0])))
        y1 = min(float(image_height), max(0.0, float(raw_box[1])))
        x2 = min(float(image_width), max(0.0, float(raw_box[2])))
        y2 = min(float(image_height), max(0.0, float(raw_box[3])))
        confidence = float(raw_box[4])
        if x2 <= x1 or y2 <= y1 or not 0 <= confidence <= 1:
            raise FaceDetectionError("face_detection_output_invalid")
        box = FaceBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1)
        landmarks = tuple(
            FacePoint(
                x=min(float(image_width - 1), max(0.0, float(point[0]))),
                y=min(float(image_height - 1), max(0.0, float(point[1]))),
            )
            for point in raw_landmarks
        )
        face = DetectedFace(
            detection_id=stable_detection_id(SCRFD_RESEARCH_MODEL_ID, box, landmarks),
            detector_id=SCRFD_RESEARCH_MODEL_ID,
            box=box,
            landmarks=landmarks,
            confidence=confidence,
        )
        existing = faces_by_id.get(face.detection_id)
        if existing is None or face.confidence > existing.confidence:
            faces_by_id[face.detection_id] = face
    return tuple(sorted(faces_by_id.values(), key=face_display_order))


def _create_scrfd_engine(
    model_path: Path,
    *,
    score_threshold: float,
    nms_threshold: float,
    input_sizes: tuple[tuple[int, int], ...],
) -> _ScrfdEngine:
    try:
        from insightface.model_zoo import model_zoo
    except ImportError as error:
        raise FaceDetectionError("face_detector_runtime_missing") from error
    try:
        raw_engine: Any = model_zoo.get_model(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        if raw_engine is None:
            raise FaceDetectionError("face_detector_load_failed")
        raw_engine.prepare(
            ctx_id=-1,
            nms_thresh=nms_threshold,
            det_thresh=score_threshold,
            input_size=list(input_sizes),
        )
    except FaceDetectionError:
        raise
    except Exception as error:
        raise FaceDetectionError("face_detector_load_failed") from error
    return cast(_ScrfdEngine, raw_engine)
