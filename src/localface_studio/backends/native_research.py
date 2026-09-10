"""Consent-gated, local InsightFace InSwapper workflow backend."""

import asyncio
import json
import logging
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
from localface_studio.application.face_processing import FaceEnhancer, FaceSwapper, SwapOutput
from localface_studio.application.task_queue import NodeReporter, WorkflowExecutionError
from localface_studio.backends.face_quality import ColorHarmonizationEnhancer
from localface_studio.backends.result_export import (
    draw_ai_watermark,
    read_result_metadata,
    save_result,
)
from localface_studio.domain.faces import DetectedFace
from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import QualityPreset, ResultVariant, TaskRecord, WorkflowNode
from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated
from localface_studio.infrastructure.logging import log_event
from localface_studio.infrastructure.model_manifest import (
    ModelArtifact,
    ModelManifestError,
    load_model_artifact,
    verify_model_artifact,
)
from localface_studio.infrastructure.resource_monitor import ResourceMonitor
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

NATIVE_RESEARCH_BACKEND_ID = "native-research"
INSWAPPER_RESEARCH_MODEL_ID = "inswapper-128-research"
ALPHAFACE_RESEARCH_MODEL_ID = "alphaface-256-research"
RESEARCH_SWAP_MODEL_IDS = frozenset({INSWAPPER_RESEARCH_MODEL_ID, ALPHAFACE_RESEARCH_MODEL_ID})
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


class InSwapperFaceSwapper:
    """Replaceable InsightFace adapter; identities live only within a single call."""

    def __init__(
        self,
        manifest_path: Path,
        project_root: Path,
        *,
        model_id: str = INSWAPPER_RESEARCH_MODEL_ID,
    ) -> None:
        if model_id not in RESEARCH_SWAP_MODEL_IDS:
            raise ValueError("unsupported research swap model")
        self._model_id = model_id
        self._manifest_path = manifest_path
        self._project_root = project_root
        self._models: tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]] | None = None
        self._verified_paths: tuple[Path, Path] | None = None
        self._model_lock = Lock()
        self._inference_lock = Lock()

    def swap(
        self,
        source: NDArray[np.uint8],
        target: NDArray[np.uint8],
        source_face: DetectedFace,
        target_face: DetectedFace,
    ) -> SwapOutput:
        with self._inference_lock:
            recognizer, swapper, providers = self._load_models()
            try:
                image = _infer_swap(recognizer, swapper, source, target, source_face, target_face)
            except Exception:
                if not providers or providers[0] != "CUDAExecutionProvider":
                    raise
                recognizer, swapper, providers = self._cpu_models()
                image = _infer_swap(recognizer, swapper, source, target, source_face, target_face)
        return SwapOutput(image=image, execution_providers=providers)

    def _load_models(self) -> tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]]:
        with self._model_lock:
            if self._models is not None:
                return self._models
            encoder_path, swap_path = self._model_paths()
            try:
                self._models = _create_engines(
                    encoder_path, swap_path, prefer_gpu=True, model_id=self._model_id
                )
            except WorkflowExecutionError:
                self._models = _create_engines(
                    encoder_path, swap_path, prefer_gpu=False, model_id=self._model_id
                )
            return self._models

    def _cpu_models(self) -> tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]]:
        with self._model_lock:
            if self._models is not None and self._models[2] == ("CPUExecutionProvider",):
                return self._models
            encoder_path, swap_path = self._model_paths()
            self._models = _create_engines(
                encoder_path, swap_path, prefer_gpu=False, model_id=self._model_id
            )
            return self._models

    def _model_paths(self) -> tuple[Path, Path]:
        if self._verified_paths is not None:
            return self._verified_paths
        encoder_artifact = load_model_artifact(self._manifest_path, ARCFACE_RESEARCH_MODEL_ID)
        swap_artifact = load_model_artifact(self._manifest_path, self._model_id)
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
            swapper = load_model_artifact(self._manifest_path, self._model_id)
            model_files_present = all(
                self._artifact_file_present(artifact) for artifact in (encoder, swapper)
            )
        except ModelManifestError:
            model_files_present = False
        # A readiness request must not block the API event loop during cold loading.
        # Sessions are published as one immutable tuple after complete construction.
        models = self._models
        providers = () if models is None else models[2]
        integrity_verified = self._verified_paths is not None
        execution_provider = "not_loaded"
        if providers:
            execution_provider = "cuda" if providers[0] == "CUDAExecutionProvider" else "cpu"
        advisories: list[str] = []
        if not model_files_present:
            advisories.append("model_files_missing")
        else:
            if not integrity_verified:
                advisories.append("integrity_check_pending")
            if not providers:
                advisories.append("runtime_load_pending")
            elif execution_provider == "cpu":
                advisories.append("cpu_fallback")
        advisories.append("research_only")
        return {
            "workflow_backend": NATIVE_RESEARCH_BACKEND_ID,
            "model_files_present": model_files_present,
            "model_integrity_verified": integrity_verified,
            "runtime_loaded": bool(providers),
            "execution_provider": execution_provider,
            "research_only": True,
            "readiness": "ready" if model_files_present else "setup_required",
            "advisories": advisories,
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

    def unload(self) -> None:
        """Release ORT sessions when switching models on a constrained local GPU."""
        with self._inference_lock, self._model_lock:
            self._models = None


class NativeResearchBackend:
    """Orchestrate real artifacts through independently injected processing adapters."""

    def __init__(
        self,
        workspaces: TaskWorkspaceStore,
        detector_resolver: Callable[[str], FaceDetector],
        manifest_path: Path,
        project_root: Path,
        *,
        swapper: FaceSwapper | None = None,
        enhancer: FaceEnhancer | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._detector_resolver = detector_resolver
        self._swapper = swapper or InSwapperFaceSwapper(manifest_path, project_root)
        self._swappers: dict[str, FaceSwapper] = {
            INSWAPPER_RESEARCH_MODEL_ID: self._swapper,
            ALPHAFACE_RESEARCH_MODEL_ID: InSwapperFaceSwapper(
                manifest_path,
                project_root,
                model_id=ALPHAFACE_RESEARCH_MODEL_ID,
            ),
        }
        self._active_model_id = INSWAPPER_RESEARCH_MODEL_ID
        self._enhancer = enhancer or ColorHarmonizationEnhancer()

    def capabilities(self) -> dict[str, object]:
        profiles = {key: adapter.capabilities() for key, adapter in self._swappers.items()}
        snapshot = dict(profiles[self._active_model_id])
        if not snapshot["model_files_present"]:
            snapshot = dict(
                next(
                    (profile for profile in profiles.values() if profile["model_files_present"]),
                    snapshot,
                )
            )
        snapshot["swap_models"] = [
            {
                "id": model_id,
                "available": profiles[model_id]["model_files_present"],
                "native_resolution": 256 if model_id == ALPHAFACE_RESEARCH_MODEL_ID else 128,
            }
            for model_id in self._swappers
        ]
        return snapshot

    def _resolve_swapper(self, model_id: str) -> FaceSwapper:
        if model_id != self._active_model_id:
            old = self._swappers[self._active_model_id]
            if isinstance(old, InSwapperFaceSwapper):
                old.unload()
            self._active_model_id = model_id
        return self._swappers[model_id]

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        await report_node(WorkflowNode.VALIDATE)
        self._validate_task(task)
        try:
            source_path = self._workspaces.input_path(task.task_id, ImageRole.SOURCE)
            target_path = self._workspaces.input_path(task.task_id, ImageRole.TARGET)
        except FileNotFoundError as error:
            raise WorkflowExecutionError("native_input_missing") from error
        await report_node(WorkflowNode.PREPARE)
        with ResourceMonitor() as monitor:
            await report_node(WorkflowNode.SWAP)
            try:
                await self._run_thread_safely(self._render_base, task, source_path, target_path)
                if task.quality_preset is QualityPreset.BALANCED:
                    await report_node(WorkflowNode.ENHANCE)
                    await self._run_thread_safely(self._render_enhanced, task, target_path)
                await report_node(WorkflowNode.INSPECT)
                await self._run_thread_safely(self._inspect, task, target_path)
            except WorkflowExecutionError:
                raise
            except (ModelManifestError, OSError, ValueError, UnidentifiedImageError) as error:
                raise WorkflowExecutionError("native_swap_failed") from error
            await report_node(WorkflowNode.EXPORT)
        # Numeric-only, local sidecar with the same retention/deletion as the artifacts.
        self._workspaces.metrics_path(task.task_id).write_text(
            json.dumps(monitor.metrics),
            encoding="utf-8",
        )
        log_event(
            logging.getLogger("localface"), logging.INFO, "native_task_completed", **monitor.metrics
        )

    @staticmethod
    def _validate_task(task: TaskRecord) -> None:
        if task.workflow_backend_id != NATIVE_RESEARCH_BACKEND_ID:
            raise WorkflowExecutionError("workflow_backend_mismatch")
        if task.swap_model_id not in RESEARCH_SWAP_MODEL_IDS:
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

    def _render_base(self, task: TaskRecord, source_path: Path, target_path: Path) -> None:
        source = decode_bgr_autorotated(source_path)
        target = decode_bgr_autorotated(target_path)
        try:
            detector = self._detector_resolver(cast(str, task.detector_id))
            source_face = _selected_face(
                detector.detect(source), cast(str, task.source_detection_id)
            )
            target_face = _selected_face(
                detector.detect(target), cast(str, task.target_detection_id)
            )
            swapper = self._resolve_swapper(cast(str, task.swap_model_id))
            output = swapper.swap(source, target, source_face, target_face)
            if output.image.dtype != np.uint8 or output.image.shape != target.shape:
                raise WorkflowExecutionError("native_output_shape_invalid")
            if np.array_equal(output.image, target):
                raise WorkflowExecutionError("native_output_unchanged")
            metadata: dict[str, object] = {
                "app": "LocalFace Studio",
                "app_version": __version__,
                "ai_edited": True,
                "backend": NATIVE_RESEARCH_BACKEND_ID,
                "created_at": datetime.now(UTC).isoformat(),
                "simulation": False,
                "detector_id": task.detector_id,
                "swap_model_id": task.swap_model_id,
                "execution_providers": list(output.execution_providers),
                "visible_watermark": task.watermark_enabled,
                "jpeg_quality": task.jpeg_quality,
                "quality_preset": task.quality_preset.value,
            }
            # Lossless unwatermarked intermediate, removed after enhancement or by queue cleanup.
            if task.quality_preset is QualityPreset.BALANCED:
                intermediate = self._workspaces.staging_path(task.task_id, ImageRole.SOURCE)
                with Image.fromarray(output.image[:, :, ::-1]) as image:
                    image.save(intermediate, format="PNG")
            self._publish(task, output.image, ResultVariant.BASE, metadata)
        finally:
            source.fill(0)
            target.fill(0)

    def _render_enhanced(self, task: TaskRecord, target_path: Path) -> None:
        target = decode_bgr_autorotated(target_path)
        intermediate = self._workspaces.staging_path(task.task_id, ImageRole.SOURCE)
        base = decode_bgr_autorotated(intermediate)
        try:
            detector = self._detector_resolver(cast(str, task.detector_id))
            face = _selected_face(detector.detect(target), cast(str, task.target_detection_id))
            enhanced = self._enhancer.enhance(target, base, face)
            if enhanced.dtype != np.uint8 or enhanced.shape != target.shape:
                raise WorkflowExecutionError("native_output_shape_invalid")
            with Image.open(
                self._workspaces.result_path(task.task_id, task.output_format, ResultVariant.BASE)
            ) as saved:
                metadata = read_result_metadata(saved, task.output_format)
            metadata["enhancer_id"] = self._enhancer.enhancer_id
            self._publish(task, enhanced, ResultVariant.ENHANCED, metadata)
        finally:
            target.fill(0)
            base.fill(0)
            intermediate.unlink(missing_ok=True)

    def _publish(
        self,
        task: TaskRecord,
        pixels: NDArray[np.uint8],
        variant: ResultVariant,
        metadata: dict[str, object],
    ) -> None:
        with Image.fromarray(np.ascontiguousarray(pixels[:, :, ::-1])).convert("RGBA") as result:
            if task.watermark_enabled:
                draw_ai_watermark(result)
            metadata = {**metadata, "result_variant": variant.value}
            staging = self._workspaces.result_staging_path(task.task_id)
            try:
                save_result(
                    result, staging, task.output_format, metadata, jpeg_quality=task.jpeg_quality
                )
                staging.replace(
                    self._workspaces.result_path(task.task_id, task.output_format, variant)
                )
            finally:
                staging.unlink(missing_ok=True)

    def _inspect(self, task: TaskRecord, target_path: Path) -> None:
        target = decode_bgr_autorotated(target_path)
        target_size = (target.shape[1], target.shape[0])
        del target
        expected = [ResultVariant.BASE]
        if task.quality_preset is QualityPreset.BALANCED:
            expected.append(ResultVariant.ENHANCED)
        for variant in expected:
            with Image.open(
                self._workspaces.result_path(task.task_id, task.output_format, variant)
            ) as result:
                result.load()
                if result.size != target_size:
                    raise ValueError("native output dimensions changed")
                metadata = read_result_metadata(result, task.output_format)
            if (
                metadata.get("simulation") is not False
                or metadata.get("ai_edited") is not True
                or metadata.get("backend") != NATIVE_RESEARCH_BACKEND_ID
                or metadata.get("swap_model_id") != task.swap_model_id
                or metadata.get("result_variant") != variant.value
                or metadata.get("visible_watermark") != task.watermark_enabled
            ):
                raise ValueError("required native result metadata is missing")


def _selected_face(faces: tuple[DetectedFace, ...], detection_id: str) -> DetectedFace:
    for face in faces:
        if face.detection_id == detection_id:
            return face
    raise WorkflowExecutionError("selected_face_not_reproduced")


def _engine_face(face: DetectedFace) -> Any:
    try:
        from insightface.app.common import Face
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
    # InSwapper needs target landmarks, not a target identity embedding.
    if getattr(source_engine_face, "normed_embedding", None) is None:
        raise WorkflowExecutionError("source_embedding_failed")
    return np.asarray(swapper.get(target, target_engine_face, source_engine_face, paste_back=True))


def _create_engines(
    encoder_path: Path,
    swap_path: Path,
    *,
    prefer_gpu: bool,
    model_id: str = INSWAPPER_RESEARCH_MODEL_ID,
) -> tuple[_RecognitionEngine, _SwapEngine, tuple[str, ...]]:
    try:
        import onnxruntime as ort
        from insightface.model_zoo import model_zoo
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
        if model_id == ALPHAFACE_RESEARCH_MODEL_ID:
            from localface_studio.backends.alphaface import AlphaFaceEngine

            swapper = AlphaFaceEngine(str(swap_path), providers)
        else:
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
