"""SCRFD research adapter license, mapping, and fail-closed tests."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from localface_studio.backends import scrfd
from localface_studio.backends.face_detection_common import FaceDetectionError
from localface_studio.backends.scrfd import ScrfdResearchFaceDetector
from localface_studio.infrastructure.model_manifest import ModelManifestError


class FakeScrfdEngine:
    def __init__(
        self,
        boxes: NDArray[np.float32],
        keypoints: NDArray[np.float32] | None,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.boxes = boxes
        self.keypoints = keypoints
        self.failure = failure
        self.calls: list[tuple[tuple[int, ...], None, int]] = []

    def detect(
        self,
        image: NDArray[np.uint8],
        input_size: None = None,
        max_num: int = 0,
    ) -> tuple[NDArray[np.float32], NDArray[np.float32] | None]:
        self.calls.append((image.shape, input_size, max_num))
        if self.failure is not None:
            raise self.failure
        return self.boxes, self.keypoints


def _keypoints(offset: float) -> list[list[float]]:
    return [
        [offset + 2, offset + 3],
        [offset + 8, offset + 3],
        [offset + 5, offset + 6],
        [offset + 3, offset + 9],
        [offset + 7, offset + 9],
    ]


def _install_fake_engine(
    monkeypatch: pytest.MonkeyPatch,
    engine: FakeScrfdEngine,
) -> None:
    monkeypatch.setattr(scrfd, "_create_scrfd_engine", lambda *args, **kwargs: engine)


def _write_manifest(tmp_path: Path, model_bytes: bytes = b"scrfd-model") -> Path:
    model_path = tmp_path / "models/det_2.5g.onnx"
    model_path.parent.mkdir()
    model_path.write_bytes(model_bytes)
    manifest = {
        "schema_version": 1,
        "models": [
            {
                "id": "scrfd-insightface-research",
                "role": "face_detector",
                "version": "test",
                "filename": "det_2.5g.onnx",
                "relative_path": "models/det_2.5g.onnx",
                "sha256": sha256(model_bytes).hexdigest(),
                "size_bytes": len(model_bytes),
                "commercial_mode_allowed": False,
            }
        ],
    }
    manifest_path = tmp_path / "models.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_scrfd_maps_clips_deduplicates_and_sorts_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boxes = np.asarray(
        [[70, 5, 120, 45, 0.97], [-5, 20, 30, 70, 0.91], [-5, 20, 30, 70, 0.95]],
        dtype=np.float32,
    )
    keypoints = np.asarray([_keypoints(75), _keypoints(5), _keypoints(5)], dtype=np.float32)
    engine = FakeScrfdEngine(boxes, keypoints)
    _install_fake_engine(monkeypatch, engine)
    detector = ScrfdResearchFaceDetector(Path("ignored.onnx"), research_license_accepted=True)

    faces = detector.detect(np.zeros((80, 100, 3), dtype=np.uint8))

    assert engine.calls == [((80, 100, 3), None, 0)]
    assert len(faces) == 2
    assert [face.confidence for face in faces] == pytest.approx([0.97, 0.95])
    assert faces[0].box.x == pytest.approx(70)
    assert faces[0].box.width == pytest.approx(30)
    assert faces[1].box.x == pytest.approx(0)
    assert len(faces[0].landmarks) == 5
    assert len({face.detection_id for face in faces}) == 2


def test_scrfd_returns_empty_and_rejects_invalid_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeScrfdEngine(np.empty((0, 5), np.float32), None)
    _install_fake_engine(monkeypatch, engine)
    detector = ScrfdResearchFaceDetector(Path("ignored.onnx"), research_license_accepted=True)

    assert detector.detect(np.zeros((40, 60, 3), dtype=np.uint8)) == ()
    with pytest.raises(FaceDetectionError, match="face_detection_image_invalid"):
        detector.detect(np.zeros((40, 60), dtype=np.uint8))


@pytest.mark.parametrize(
    ("boxes", "keypoints", "error_code"),
    [
        (
            np.asarray([[1, 1, 10, 10, 0.9]], np.float32),
            None,
            "face_detection_landmarks_missing",
        ),
        (
            np.asarray([[1, 1, 10, 10, 1.1]], np.float32),
            np.asarray([_keypoints(1)], np.float32),
            "face_detection_output_invalid",
        ),
        (
            np.asarray([[10, 10, 1, 1, 0.9]], np.float32),
            np.asarray([_keypoints(1)], np.float32),
            "face_detection_output_invalid",
        ),
    ],
)
def test_scrfd_rejects_invalid_detector_output(
    monkeypatch: pytest.MonkeyPatch,
    boxes: NDArray[np.float32],
    keypoints: NDArray[np.float32] | None,
    error_code: str,
) -> None:
    _install_fake_engine(monkeypatch, FakeScrfdEngine(boxes, keypoints))
    detector = ScrfdResearchFaceDetector(Path("ignored.onnx"), research_license_accepted=True)

    with pytest.raises(FaceDetectionError, match=error_code):
        detector.detect(np.zeros((40, 60, 3), dtype=np.uint8))


def test_scrfd_wraps_runtime_failure_and_rejects_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeScrfdEngine(
        np.empty((0, 5), np.float32),
        None,
        failure=RuntimeError("private runtime detail"),
    )
    _install_fake_engine(monkeypatch, engine)

    with pytest.raises(ValueError, match="score_threshold"):
        ScrfdResearchFaceDetector(
            Path("ignored.onnx"),
            research_license_accepted=True,
            score_threshold=0,
        )
    with pytest.raises(ValueError, match="input_sizes"):
        ScrfdResearchFaceDetector(
            Path("ignored.onnx"),
            research_license_accepted=True,
            input_sizes=((16, 16),),
        )
    detector = ScrfdResearchFaceDetector(Path("ignored.onnx"), research_license_accepted=True)
    with pytest.raises(FaceDetectionError, match="face_detection_inference_failed"):
        detector.detect(np.zeros((40, 60, 3), dtype=np.uint8))


def test_scrfd_manifest_requires_research_acceptance_and_rejects_commercial_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_manifest(tmp_path)
    engine = FakeScrfdEngine(np.empty((0, 5), np.float32), None)
    _install_fake_engine(monkeypatch, engine)

    with pytest.raises(ModelManifestError, match="model_license_not_accepted"):
        ScrfdResearchFaceDetector(Path("ignored.onnx"))
    with pytest.raises(ModelManifestError, match="model_not_allowed_in_commercial_mode"):
        ScrfdResearchFaceDetector(
            Path("ignored.onnx"),
            commercial_mode=True,
            research_license_accepted=True,
        )
    with pytest.raises(ModelManifestError, match="model_license_not_accepted"):
        ScrfdResearchFaceDetector.from_manifest(manifest_path, tmp_path)
    with pytest.raises(ModelManifestError, match="model_not_allowed_in_commercial_mode"):
        ScrfdResearchFaceDetector.from_manifest(
            manifest_path,
            tmp_path,
            commercial_mode=True,
            research_license_accepted=True,
        )

    detector = ScrfdResearchFaceDetector.from_manifest(
        manifest_path,
        tmp_path,
        research_license_accepted=True,
    )
    assert detector.detector_id == "scrfd-insightface-research"


def test_scrfd_manifest_verifies_model_before_engine_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_manifest(tmp_path)
    model_path = tmp_path / "models/det_2.5g.onnx"
    model_path.write_bytes(b"tampered-model")
    created = False

    def create_engine(*args: object, **kwargs: object) -> FakeScrfdEngine:
        nonlocal created
        created = True
        return FakeScrfdEngine(np.empty((0, 5), np.float32), None)

    monkeypatch.setattr(scrfd, "_create_scrfd_engine", create_engine)

    with pytest.raises(ModelManifestError, match="model_size_mismatch"):
        ScrfdResearchFaceDetector.from_manifest(
            manifest_path,
            tmp_path,
            research_license_accepted=True,
        )
    assert not created

    model_path.unlink()
    with pytest.raises(ModelManifestError, match="model_file_missing"):
        ScrfdResearchFaceDetector.from_manifest(
            manifest_path,
            tmp_path,
            research_license_accepted=True,
        )
    assert not created
