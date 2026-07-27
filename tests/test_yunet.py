"""YuNet adapter coordinate, ordering, resizing, and error tests."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from localface_studio.backends import yunet
from localface_studio.backends.yunet import FaceDetectionError, YuNetFaceDetector
from localface_studio.infrastructure.model_manifest import ModelManifestError


class FakeYuNetEngine:
    def __init__(self, rows: NDArray[np.float32] | None, *, status: int = 1) -> None:
        self.rows = rows
        self.status = status
        self.input_sizes: list[tuple[int, int]] = []
        self.image_shapes: list[tuple[int, ...]] = []

    def setInputSize(self, input_size: tuple[int, int]) -> None:
        self.input_sizes.append(input_size)

    def detect(
        self,
        image: NDArray[np.uint8],
    ) -> tuple[int, NDArray[np.float32] | None]:
        self.image_shapes.append(image.shape)
        return self.status, self.rows


def row(x: float, y: float, confidence: float) -> list[float]:
    return [
        x,
        y,
        50,
        60,
        x + 10,
        y + 15,
        x + 35,
        y + 15,
        x + 25,
        y + 30,
        x + 15,
        y + 45,
        x + 35,
        y + 45,
        confidence,
    ]


def test_yunet_resizes_for_inference_maps_back_and_sorts_geometrically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeYuNetEngine(np.asarray([row(100, 100, 0.91), row(200, 20, 0.97)], np.float32))
    monkeypatch.setattr(yunet, "_create_yunet_engine", lambda *args, **kwargs: engine)
    detector = YuNetFaceDetector(Path("ignored.onnx"), maximum_input_edge=1000)

    faces = detector.detect(np.zeros((2000, 4000, 3), dtype=np.uint8))

    assert engine.input_sizes == [(1000, 500)]
    assert engine.image_shapes == [(500, 1000, 3)]
    assert [face.confidence for face in faces] == pytest.approx([0.97, 0.91])
    assert faces[0].box.x == pytest.approx(800)
    assert faces[0].box.y == pytest.approx(80)
    assert faces[0].box.width == pytest.approx(200)
    assert len({face.detection_id for face in faces}) == 2


def test_yunet_returns_empty_and_rejects_invalid_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeYuNetEngine(None)
    monkeypatch.setattr(yunet, "_create_yunet_engine", lambda *args, **kwargs: engine)
    detector = YuNetFaceDetector(Path("ignored.onnx"))

    assert detector.detect(np.zeros((40, 60, 3), dtype=np.uint8)) == ()
    with pytest.raises(FaceDetectionError, match="face_detection_image_invalid"):
        detector.detect(np.zeros((40, 60), dtype=np.uint8))


def test_yunet_rejects_invalid_configuration_and_failed_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeYuNetEngine(None, status=0)
    monkeypatch.setattr(yunet, "_create_yunet_engine", lambda *args, **kwargs: engine)

    with pytest.raises(ValueError, match="score_threshold"):
        YuNetFaceDetector(Path("ignored.onnx"), score_threshold=0)
    with pytest.raises(ValueError, match="outside supported bounds"):
        YuNetFaceDetector(Path("ignored.onnx"), top_k=0)
    detector = YuNetFaceDetector(Path("ignored.onnx"))
    with pytest.raises(FaceDetectionError, match="face_detection_inference_failed"):
        detector.detect(np.zeros((40, 60, 3), dtype=np.uint8))


def test_yunet_rejects_non_finite_or_impossible_detector_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_rows = np.asarray([row(10, 10, float("nan"))], np.float32)
    engine = FakeYuNetEngine(invalid_rows)
    monkeypatch.setattr(yunet, "_create_yunet_engine", lambda *args, **kwargs: engine)
    detector = YuNetFaceDetector(Path("ignored.onnx"))

    with pytest.raises(FaceDetectionError, match="face_detection_output_invalid"):
        detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    engine.rows = np.asarray([row(150, 150, 0.95)], np.float32)
    with pytest.raises(FaceDetectionError, match="face_detection_output_invalid"):
        detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))


def test_from_manifest_verifies_hash_before_creating_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_bytes = b"valid-model"
    model_path = tmp_path / "models/model.onnx"
    model_path.parent.mkdir()
    model_path.write_bytes(model_bytes)
    manifest = {
        "schema_version": 1,
        "models": [
            {
                "id": "yunet-opencv",
                "role": "face_detector",
                "version": "test",
                "filename": "model.onnx",
                "relative_path": "models/model.onnx",
                "sha256": sha256(model_bytes).hexdigest(),
                "size_bytes": len(model_bytes),
                "commercial_mode_allowed": True,
            }
        ],
    }
    manifest_path = tmp_path / "models.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    engine = FakeYuNetEngine(None)
    monkeypatch.setattr(yunet, "_create_yunet_engine", lambda *args, **kwargs: engine)

    detector = YuNetFaceDetector.from_manifest(manifest_path, tmp_path, commercial_mode=True)

    assert detector.detector_id == "yunet-opencv"
    model_path.write_bytes(b"tampered!!!")
    with pytest.raises(ModelManifestError, match="model_hash_mismatch"):
        YuNetFaceDetector.from_manifest(manifest_path, tmp_path)
