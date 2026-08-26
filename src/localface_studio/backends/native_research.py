"""Consent-gated, local InsightFace InSwapper workflow backend."""

import asyncio
import os
import site
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from localface_studio import __version__
from localface_studio.application.face_detection import FaceDetector
from localface_studio.application.task_queue import NodeReporter, WorkflowExecutionError
from localface_studio.backends.result_export import (
    draw_ai_watermark,
    read_result_metadata,
    save_result,
)
from localface_studio.domain.faces import DetectedFace
from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import TaskRecord, WorkflowNode
from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated
from localface_studio.infrastructure.model_manifest import (
    ModelArtifact,
    ModelManifestError,
    load_model_artifact,
    verify_model_artifact,
)
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

NATIVE_RESEARCH_BACKEND_ID = "native-research"
INSWAPPER_RESEARCH_MODEL_ID = "inswapper-128-research"
ARCFACE_RESEARCH_MODEL_ID = "arcface-w600k-r50-research"
_DLL_DIRECTORY_HANDLES: list[Any] = []


class _RecognitionEngine(Protocol):
    def prepare(self, ctx_id: int) -> None: ...

    def get(self, image: NDArray[np.uint8], face: Any) -> Any: ...


class _SwapEngine(Protocol):
    def get(
        self,
        image: NDArray[np.uint8],
        target_face: Any,
        source_face: Any,
        *,
        paste_back: bool,
    ) -> NDArray[np.uint8]: ...


class NativeResearchBackend:
    """Run one selected-face swap locally and publish only an inspected result."""

    def __init__(
        self,
        workspaces: TaskWorkspaceStore,
        detector_resolver: Callable[[str], FaceDetector],
        manifest_path: Path,
        project_root: Path,
    ) -> None:
        self._workspaces = workspaces
        self._detector_resolver = detector_resolver
        self._manifest_path = manifest_path
        self._project_root = project_root
        self._models: tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]] | None = None
        self._verified_paths: tuple[Path, Path] | None = None
        self._model_lock = Lock()
        self._inference_lock = Lock()

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        await report_node(WorkflowNode.VALIDATE)
        self._validate_task(task)
        try:
            source_path = self._workspaces.input_path(task.task_id, ImageRole.SOURCE)
            target_path = self._workspaces.input_path(task.task_id, ImageRole.TARGET)
        except FileNotFoundError as error:
            raise WorkflowExecutionError("native_input_missing") from error

        await report_node(WorkflowNode.PREPARE)
        await report_node(WorkflowNode.SWAP)
        try:
            await self._run_thread_safely(self._render, task, source_path, target_path)
        except WorkflowExecutionError:
            raise
        except (ModelManifestError, OSError, ValueError, UnidentifiedImageError) as error:
            raise WorkflowExecutionError("native_swap_failed") from error

        await report_node(WorkflowNode.INSPECT)
        try:
            await self._run_thread_safely(self._inspect, task, target_path)
        except (OSError, ValueError, UnidentifiedImageError) as error:
            raise WorkflowExecutionError("native_output_invalid") from error
        await report_node(WorkflowNode.EXPORT)

    @staticmethod
    def _validate_task(task: TaskRecord) -> None:
        if task.workflow_backend_id != NATIVE_RESEARCH_BACKEND_ID:
            raise WorkflowExecutionError("workflow_backend_mismatch")
        if task.swap_model_id != INSWAPPER_RESEARCH_MODEL_ID:
            raise WorkflowExecutionError("swap_model_mismatch")
        if task.research_model_license_accepted is not True:
            raise WorkflowExecutionError("research_model_license_not_accepted")
        if (
            task.detector_id is None
            or task.source_detection_id is None
            or task.target_detection_id is None
        ):
            raise WorkflowExecutionError("face_selection_missing")

    @staticmethod
    async def _run_thread_safely(function: Callable[..., None], *args: object) -> None:
        worker = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            with suppress(Exception):
                await worker
            raise

    def _render(self, task: TaskRecord, source_path: Path, target_path: Path) -> None:
        source = decode_bgr_autorotated(source_path)
        target = decode_bgr_autorotated(target_path)
        detector = self._detector_resolver(cast(str, task.detector_id))
        source_face = _selected_face(detector.detect(source), cast(str, task.source_detection_id))
        target_face = _selected_face(detector.detect(target), cast(str, task.target_detection_id))
        recognizer, swapper, providers = self._load_models()
        with self._inference_lock:
            try:
                swapped = _infer_swap(recognizer, swapper, source, target, source_face, target_face)
            except Exception:
                if not providers or providers[0] != "CUDAExecutionProvider":
                    raise
                recognizer, swapper, providers = self._cpu_models()
                swapped = _infer_swap(recognizer, swapper, source, target, source_face, target_face)
        if swapped.dtype != np.uint8 or swapped.shape != target.shape:
            raise WorkflowExecutionError("native_output_shape_invalid")

        result = Image.fromarray(
            np.ascontiguousarray(swapped[:, :, ::-1]),
            mode="RGB",
        ).convert("RGBA")
        if task.watermark_enabled:
            draw_ai_watermark(result)
        metadata: dict[str, object] = {
            "app": "LocalFace Studio",
            "app_version": __version__,
            "ai_edited": True,
            "backend": NATIVE_RESEARCH_BACKEND_ID,
            "created_at": datetime.now(UTC).isoformat(),
            "simulation": False,
            "detector_id": task.detector_id,
            "swap_model_id": task.swap_model_id,
            "execution_providers": list(providers),
            "visible_watermark": task.watermark_enabled,
            "jpeg_quality": task.jpeg_quality,
        }
        staging_path = self._workspaces.result_staging_path(task.task_id)
        result_path = self._workspaces.result_path(task.task_id, task.output_format)
        if staging_path.exists():
            staging_path.unlink()
        try:
            save_result(
                result,
                staging_path,
                task.output_format,
                metadata,
                jpeg_quality=task.jpeg_quality,
            )
            staging_path.replace(result_path)
        finally:
            if staging_path.exists():
                staging_path.unlink()
            source.fill(0)
            target.fill(0)

    def _load_models(self) -> tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]]:
        with self._model_lock:
            if self._models is not None:
                return self._models
            encoder_path, swap_path = self._model_paths()
            self._models = _create_engines(encoder_path, swap_path, prefer_gpu=True)
            return self._models

    def _cpu_models(self) -> tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]]:
        with self._model_lock:
            if self._models is not None and self._models[2] == ("CPUExecutionProvider",):
                return self._models
            encoder_path, swap_path = self._model_paths()
            self._models = _create_engines(encoder_path, swap_path, prefer_gpu=False)
            return self._models

    def _model_paths(self) -> tuple[Path, Path]:
        if self._verified_paths is not None:
            return self._verified_paths
        encoder_artifact = load_model_artifact(self._manifest_path, ARCFACE_RESEARCH_MODEL_ID)
        swap_artifact = load_model_artifact(self._manifest_path, INSWAPPER_RESEARCH_MODEL_ID)
        if encoder_artifact.role != "face_encoder" or swap_artifact.role != "face_swapper":
            raise ModelManifestError("model_role_mismatch")
        if encoder_artifact.commercial_mode_allowed or swap_artifact.commercial_mode_allowed:
            raise ModelManifestError("research_model_policy_mismatch")
        self._verified_paths = (
            verify_model_artifact(encoder_artifact, self._project_root),
            verify_model_artifact(swap_artifact, self._project_root),
        )
        return self._verified_paths

    def capabilities(self) -> dict[str, object]:
        """Return a fast, privacy-safe readiness snapshot without loading models."""
        try:
            encoder = load_model_artifact(self._manifest_path, ARCFACE_RESEARCH_MODEL_ID)
            swapper = load_model_artifact(self._manifest_path, INSWAPPER_RESEARCH_MODEL_ID)
            model_files_present = all(
                self._artifact_file_present(artifact) for artifact in (encoder, swapper)
            )
        except ModelManifestError:
            model_files_present = False
        with self._model_lock:
            providers = () if self._models is None else self._models[2]
            integrity_verified = self._verified_paths is not None
        execution_provider = "not_loaded"
        if providers:
            execution_provider = "cuda" if providers[0] == "CUDAExecutionProvider" else "cpu"
        return {
            "workflow_backend": NATIVE_RESEARCH_BACKEND_ID,
            "model_files_present": model_files_present,
            "model_integrity_verified": integrity_verified,
            "runtime_loaded": bool(providers),
            "execution_provider": execution_provider,
            "research_only": True,
        }

    def _artifact_file_present(self, artifact: ModelArtifact) -> bool:
        root = self._project_root.resolve()
        model_path = (root / artifact.relative_path).resolve()
        try:
            return (
                model_path.is_relative_to(root)
                and model_path.is_file()
                and model_path.stat().st_size == artifact.size_bytes
            )
        except OSError:
            return False

    def _inspect(self, task: TaskRecord, target_path: Path) -> None:
        result_path = self._workspaces.result_path(task.task_id, task.output_format)
        with Image.open(target_path) as target:
            target_size = target.size
        with Image.open(result_path) as result:
            result.load()
            if result.size != target_size:
                raise ValueError("native output dimensions changed")
            metadata = read_result_metadata(result, task.output_format)
        if (
            metadata.get("simulation") is not False
            or metadata.get("ai_edited") is not True
            or metadata.get("backend") != NATIVE_RESEARCH_BACKEND_ID
            or metadata.get("swap_model_id") != INSWAPPER_RESEARCH_MODEL_ID
        ):
            raise ValueError("required native result metadata is missing")


def _selected_face(faces: tuple[DetectedFace, ...], detection_id: str) -> DetectedFace:
    for face in faces:
        if face.detection_id == detection_id:
            return face
    raise WorkflowExecutionError("selected_face_not_reproduced")


def _engine_face(face: DetectedFace) -> Any:
    try:
        from insightface.app.common import Face  # type: ignore[import-untyped]
    except ImportError as error:
        raise WorkflowExecutionError("face_swap_runtime_missing") from error
    box = face.box
    return Face(
        bbox=np.asarray([box.x, box.y, box.x + box.width, box.y + box.height], dtype=np.float32),
        kps=np.asarray([(point.x, point.y) for point in face.landmarks], dtype=np.float32),
        det_score=float(face.confidence),
    )


def _infer_swap(
    recognizer: _RecognitionEngine,
    swapper: _SwapEngine,
    source: NDArray[np.uint8],
    target: NDArray[np.uint8],
    source_face: DetectedFace,
    target_face: DetectedFace,
) -> NDArray[np.uint8]:
    source_engine_face = _engine_face(source_face)
    target_engine_face = _engine_face(target_face)
    recognizer.get(source, source_engine_face)
    recognizer.get(target, target_engine_face)
    if getattr(source_engine_face, "normed_embedding", None) is None:
        raise WorkflowExecutionError("source_embedding_failed")
    return np.asarray(swapper.get(target, target_engine_face, source_engine_face, paste_back=True))


def _create_engines(
    encoder_path: Path,
    swap_path: Path,
    *,
    prefer_gpu: bool,
) -> tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]]:
    try:
        import onnxruntime as ort  # type: ignore[import-untyped]
        from insightface.model_zoo import model_zoo  # type: ignore[import-untyped]
    except ImportError as error:
        raise WorkflowExecutionError("face_swap_runtime_missing") from error
    try:
        _register_nvidia_dll_directories()
        preload = getattr(ort, "preload_dlls", None)
        if callable(preload):
            preload(directory="")
        available = set(ort.get_available_providers())
        use_gpu = prefer_gpu and "CUDAExecutionProvider" in available
        providers: list[Any] = (
            [
                (
                    "CUDAExecutionProvider",
                    {"cudnn_conv_algo_search": "HEURISTIC"},
                ),
                "CPUExecutionProvider",
            ]
            if use_gpu
            else ["CPUExecutionProvider"]
        )
        recognizer = model_zoo.get_model(str(encoder_path), providers=providers)
        swapper = model_zoo.get_model(str(swap_path), providers=providers)
        if recognizer is None or swapper is None:
            raise WorkflowExecutionError("face_swap_model_load_failed")
        recognizer.prepare(ctx_id=0 if use_gpu else -1)
        for engine in (recognizer, swapper):
            disable_fallback = getattr(engine.session, "disable_fallback", None)
            if callable(disable_fallback):
                disable_fallback()
        actual = tuple(str(value) for value in swapper.session.get_providers())
        expected_provider = "CUDAExecutionProvider" if use_gpu else "CPUExecutionProvider"
        if not actual or actual[0] != expected_provider:
            raise WorkflowExecutionError("face_swap_provider_unavailable")
    except WorkflowExecutionError:
        raise
    except Exception as error:
        raise WorkflowExecutionError("face_swap_model_load_failed") from error
    return cast(_RecognitionEngine, recognizer), cast(_SwapEngine, swapper), actual


def _register_nvidia_dll_directories() -> None:
    """Keep Windows DLL search handles alive for NVIDIA namespace packages."""
    if os.name != "nt" or _DLL_DIRECTORY_HANDLES:
        return
    registered: list[str] = []
    for package_root in site.getsitepackages():
        nvidia_root = Path(package_root) / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for bin_directory in sorted(nvidia_root.glob("*/bin")):
            if bin_directory.is_dir():
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(bin_directory)))
                registered.append(str(bin_directory))
    if registered:
        os.environ["PATH"] = os.pathsep.join((*registered, os.environ.get("PATH", "")))
