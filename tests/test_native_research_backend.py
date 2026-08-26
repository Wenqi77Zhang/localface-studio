"""Native research workflow tests without loading third-party model weights."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

import localface_studio.backends.native_research as native_module
from localface_studio.application.task_queue import WorkflowExecutionError
from localface_studio.backends.native_research import (
    INSWAPPER_RESEARCH_MODEL_ID,
    NATIVE_RESEARCH_BACKEND_ID,
    NativeResearchBackend,
)
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    stable_detection_id,
)
from localface_studio.domain.tasks import (
    OutputFormat,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
)
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

DETECTOR_ID = "fake-detector"


class FakeDetector:
    detector_id = DETECTOR_ID

    def __init__(self, faces: tuple[DetectedFace, ...]) -> None:
        self._faces = faces

    def detect(self, image: np.ndarray) -> tuple[DetectedFace, ...]:
        assert image.dtype == np.uint8
        return self._faces


class FakeRecognizer:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def prepare(self, ctx_id: int) -> None:
        del ctx_id

    def get(self, image: np.ndarray, face: Any) -> Any:
        if self._fail:
            raise RuntimeError("provider failed")
        assert image.dtype == np.uint8
        face.normed_embedding = np.ones(512, dtype=np.float32)
        return face


class FakeSwapper:
    def get(
        self,
        image: np.ndarray,
        target_face: Any,
        source_face: Any,
        *,
        paste_back: bool,
    ) -> np.ndarray:
        assert paste_back is True
        assert target_face.normed_embedding is not None
        assert source_face.normed_embedding is not None
        result = image.copy()
        result[2:10, 2:10] = (10, 40, 90)
        return result


def _face(x: float) -> DetectedFace:
    box = FaceBox(x=x, y=2, width=8, height=8)
    landmarks = tuple(FacePoint(x=x + index, y=3 + index / 2) for index in range(5))
    return DetectedFace(
        detection_id=stable_detection_id(DETECTOR_ID, box, landmarks),
        detector_id=DETECTOR_ID,
        box=box,
        landmarks=landmarks,
        confidence=0.98,
    )


def _task(source_face: DetectedFace, target_face: DetectedFace, **changes: Any) -> TaskRecord:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "task_id": "a" * 32,
        "actor_id": "actor",
        "status": TaskStatus.QUEUED,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(minutes=30),
        "consent_version": "test-v1",
        "consented_at": now,
        "output_format": OutputFormat.PNG,
        "watermark_enabled": True,
        "detector_id": DETECTOR_ID,
        "source_detection_id": source_face.detection_id,
        "target_detection_id": target_face.detection_id,
        "workflow_backend_id": NATIVE_RESEARCH_BACKEND_ID,
        "swap_model_id": INSWAPPER_RESEARCH_MODEL_ID,
        "research_model_license_accepted": True,
    }
    values.update(changes)
    return TaskRecord(**values)


def _prepare_store(tmp_path: Path, task: TaskRecord) -> TaskWorkspaceStore:
    store = TaskWorkspaceStore(tmp_path / "tasks")
    workspace = store.create(task.task_id)
    Image.new("RGB", (16, 14), (25, 50, 75)).save(workspace / "source.png")
    Image.new("RGB", (18, 16), (100, 120, 140)).save(workspace / "target.png")
    return store


def test_native_backend_exports_selected_swap_and_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_face = _face(2)
    target_face = _face(3)
    task = _task(source_face, target_face)
    store = _prepare_store(tmp_path, task)
    backend = NativeResearchBackend(
        store,
        lambda _: FakeDetector((source_face, target_face)),
        tmp_path / "models.json",
        tmp_path,
    )
    monkeypatch.setattr(
        backend,
        "_load_models",
        lambda: (FakeRecognizer(), FakeSwapper(), ("CUDAExecutionProvider",)),
    )
    monkeypatch.setattr(native_module, "_engine_face", lambda _: SimpleNamespace())
    nodes: list[WorkflowNode] = []

    async def report(node: WorkflowNode) -> None:
        nodes.append(node)

    asyncio.run(backend.run(task, report))

    result_path = store.result_path(task.task_id, OutputFormat.PNG)
    with Image.open(result_path) as result:
        result.load()
        metadata = json.loads(str(result.info["LocalFaceStudio"]))
        assert result.size == (18, 16)
    assert metadata["simulation"] is False
    assert metadata["backend"] == NATIVE_RESEARCH_BACKEND_ID
    assert metadata["execution_providers"] == ["CUDAExecutionProvider"]
    assert nodes == [
        WorkflowNode.VALIDATE,
        WorkflowNode.PREPARE,
        WorkflowNode.SWAP,
        WorkflowNode.INSPECT,
        WorkflowNode.EXPORT,
    ]


def test_native_backend_rebuilds_cpu_models_after_gpu_inference_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    face = _face(2)
    task = _task(face, face, watermark_enabled=False)
    store = _prepare_store(tmp_path, task)
    backend = NativeResearchBackend(
        store,
        lambda _: FakeDetector((face,)),
        tmp_path / "models.json",
        tmp_path,
    )
    monkeypatch.setattr(
        backend,
        "_load_models",
        lambda: (FakeRecognizer(fail=True), FakeSwapper(), ("CUDAExecutionProvider",)),
    )
    monkeypatch.setattr(
        backend,
        "_cpu_models",
        lambda: (FakeRecognizer(), FakeSwapper(), ("CPUExecutionProvider",)),
    )
    monkeypatch.setattr(native_module, "_engine_face", lambda _: SimpleNamespace())

    asyncio.run(backend.run(task, lambda _: asyncio.sleep(0)))

    with Image.open(store.result_path(task.task_id, OutputFormat.PNG)) as result:
        metadata = json.loads(str(result.info["LocalFaceStudio"]))
    assert metadata["execution_providers"] == ["CPUExecutionProvider"]


def test_native_backend_rejects_unreproducible_selection_without_result(tmp_path: Path) -> None:
    selected = _face(2)
    task = _task(selected, selected)
    store = _prepare_store(tmp_path, task)
    backend = NativeResearchBackend(
        store,
        lambda _: FakeDetector((_face(6),)),
        tmp_path / "models.json",
        tmp_path,
    )

    with pytest.raises(WorkflowExecutionError, match="selected_face_not_reproduced"):
        asyncio.run(backend.run(task, lambda _: asyncio.sleep(0)))
    assert not store.result_path(task.task_id, OutputFormat.PNG).exists()


def test_native_task_contract_requires_research_license_and_model() -> None:
    face = _face(2)
    with pytest.raises(ValueError, match="license acceptance"):
        _task(face, face, research_model_license_accepted=False)
    with pytest.raises(ValueError, match="swap model"):
        _task(face, face, swap_model_id=None)


def test_native_capabilities_check_files_without_loading_models(tmp_path: Path) -> None:
    encoder = b"encoder"
    swapper = b"swapper"
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "encoder.onnx").write_bytes(encoder)
    (tmp_path / "models" / "swapper.onnx").write_bytes(swapper)
    manifest = {
        "schema_version": 1,
        "models": [
            {
                "id": "arcface-w600k-r50-research",
                "role": "face_encoder",
                "version": "test",
                "filename": "encoder.onnx",
                "relative_path": "models/encoder.onnx",
                "sha256": sha256(encoder).hexdigest(),
                "size_bytes": len(encoder),
                "commercial_mode_allowed": False,
            },
            {
                "id": "inswapper-128-research",
                "role": "face_swapper",
                "version": "test",
                "filename": "swapper.onnx",
                "relative_path": "models/swapper.onnx",
                "sha256": sha256(swapper).hexdigest(),
                "size_bytes": len(swapper),
                "commercial_mode_allowed": False,
            },
        ],
    }
    manifest_path = tmp_path / "models.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    backend = NativeResearchBackend(
        TaskWorkspaceStore(tmp_path / "tasks"),
        lambda _: FakeDetector(()),
        manifest_path,
        tmp_path,
    )

    assert backend.capabilities() == {
        "workflow_backend": NATIVE_RESEARCH_BACKEND_ID,
        "model_files_present": True,
        "model_integrity_verified": False,
        "runtime_loaded": False,
        "execution_provider": "not_loaded",
        "research_only": True,
    }

    (tmp_path / "models" / "swapper.onnx").write_bytes(b"wrong size")
    assert backend.capabilities()["model_files_present"] is False
