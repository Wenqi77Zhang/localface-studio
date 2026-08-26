"""Run a consent-gated local multi-case native swap quality benchmark."""

import argparse
import asyncio
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from localface_studio.application.face_detection import FaceDetector
from localface_studio.backends.face_quality import face_blend_mask
from localface_studio.backends.native_research import (
    ARCFACE_RESEARCH_MODEL_ID,
    INSWAPPER_RESEARCH_MODEL_ID,
    NATIVE_RESEARCH_BACKEND_ID,
    NativeResearchBackend,
)
from localface_studio.backends.scrfd import (
    SCRFD_RESEARCH_MODEL_ID,
    ScrfdResearchFaceDetector,
)
from localface_studio.benchmarking.face_swap_quality import (
    cosine_similarity,
    landmark_nrmse,
    match_output_face,
    outside_face_change_ratio,
)
from localface_studio.domain.faces import DetectedFace
from localface_studio.domain.tasks import (
    OutputFormat,
    QualityPreset,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
    new_task_id,
)
from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated
from localface_studio.infrastructure.model_manifest import (
    load_model_artifact,
    verify_model_artifact,
)
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    source: Path
    target: Path
    source_face: int
    target_face: int


class ArcFaceEvaluator:
    """Local CPU identity evaluator isolated from the product task metadata."""

    def __init__(self, manifest: Path) -> None:
        artifact = load_model_artifact(manifest, ARCFACE_RESEARCH_MODEL_ID)
        model_path = verify_model_artifact(artifact, ROOT)
        try:
            from insightface.model_zoo import model_zoo
        except ImportError as error:
            raise RuntimeError("InsightFace evaluation runtime is missing.") from error
        model = model_zoo.get_model(str(model_path), providers=["CPUExecutionProvider"])
        if model is None:
            raise RuntimeError("ArcFace evaluator could not be loaded.")
        model.prepare(ctx_id=-1)
        self._model: Any = model

    def embedding(
        self,
        image: NDArray[np.uint8],
        face: DetectedFace,
    ) -> NDArray[np.float32]:
        try:
            from insightface.app.common import Face
        except ImportError as error:
            raise RuntimeError("InsightFace evaluation runtime is missing.") from error
        box = face.box
        engine_face = Face(
            bbox=np.asarray(
                [box.x, box.y, box.x + box.width, box.y + box.height],
                dtype=np.float32,
            ),
            kps=np.asarray([(point.x, point.y) for point in face.landmarks], dtype=np.float32),
            det_score=float(face.confidence),
        )
        self._model.get(image, engine_face)
        embedding = getattr(engine_face, "normed_embedding", None)
        if embedding is None:
            raise RuntimeError("ArcFace did not return an embedding.")
        return np.asarray(embedding, dtype=np.float32)


def main() -> None:
    args = parse_args()
    if not args.confirm_image_authorization or not args.accept_research_license:
        raise SystemExit("Pass both --confirm-image-authorization and --accept-research-license.")
    cases = load_cases(Path(args.cases))
    asyncio.run(run_benchmark(cases, Path(args.output_directory), Path(args.report)))


async def run_benchmark(
    cases: tuple[BenchmarkCase, ...],
    output_directory: Path,
    report_path: Path,
) -> None:
    manifest = ROOT / "config" / "models.json"
    work_root = ROOT / ".tools" / "native-quality-benchmark"
    if work_root.exists():
        shutil.rmtree(work_root)
    store = TaskWorkspaceStore(work_root)
    detector = ScrfdResearchFaceDetector.from_manifest(
        manifest,
        ROOT,
        research_license_accepted=True,
    )
    backend = NativeResearchBackend(store, lambda _: detector, manifest, ROOT)
    output_directory.mkdir(parents=True, exist_ok=True)
    case_reports: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    try:
        generated: list[
            tuple[
                BenchmarkCase,
                NDArray[np.uint8],
                NDArray[np.uint8],
                DetectedFace,
                DetectedFace,
                dict[QualityPreset, tuple[NDArray[np.uint8], float]],
            ]
        ] = []
        for case in cases:
            try:
                source = decode_bgr_autorotated(case.source)
                target = decode_bgr_autorotated(case.target)
                source_face = _indexed_face(detector, source, case.source_face, case.case_id)
                target_face = _indexed_face(detector, target, case.target_face, case.case_id)
                results: dict[QualityPreset, tuple[NDArray[np.uint8], float]] = {}
                for preset in QualityPreset:
                    output, duration = await _run_swap(
                        backend,
                        store,
                        source,
                        target,
                        source_face,
                        target_face,
                        detector.detector_id,
                        preset,
                    )
                    results[preset] = (output, duration)
                    cv2.imwrite(
                        str(output_directory / f"{case.case_id}-{preset.value}.png"), output
                    )
                generated.append((case, source, target, source_face, target_face, results))
            except Exception as error:
                failures.append({"case_id": case.case_id, "error_type": type(error).__name__})

        evaluator = ArcFaceEvaluator(manifest)
        for case, source, target, source_face, target_face, results in generated:
            try:
                source_embedding = evaluator.embedding(source, source_face)
                target_embedding = evaluator.embedding(target, target_face)
                presets: dict[str, object] = {}
                for preset, (output, duration) in results.items():
                    output_face = match_output_face(target_face, detector.detect(output))
                    output_embedding = evaluator.embedding(output, output_face)
                    presets[preset.value] = _preset_metrics(
                        target,
                        output,
                        target_face,
                        output_face,
                        source_embedding,
                        output_embedding,
                        duration,
                    )
                case_reports.append(
                    {
                        "case_id": case.case_id,
                        "source_to_target_identity_cosine": _round(
                            cosine_similarity(source_embedding, target_embedding)
                        ),
                        "presets": presets,
                    }
                )
            except Exception as error:
                failures.append({"case_id": case.case_id, "error_type": type(error).__name__})
    finally:
        if work_root.exists():
            shutil.rmtree(work_root)

    report = {
        "schema_version": 1,
        "detector_id": SCRFD_RESEARCH_MODEL_ID,
        "swap_model_id": INSWAPPER_RESEARCH_MODEL_ID,
        "identity_model_id": ARCFACE_RESEARCH_MODEL_ID,
        "case_count": len(cases),
        "successful_cases": len(case_reports),
        "successful_swaps": len(case_reports) * len(QualityPreset),
        "execution_provider": backend.capabilities()["execution_provider"],
        "failures": failures,
        "summary": summarize(case_reports),
        "cases": case_reports,
        "limitations": [
            "ArcFace similarity is a model-based proxy, not proof of human identity.",
            "The local authorized set is small and not a fairness or population benchmark.",
            "Pixel metrics are computed without a visible watermark.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], separators=(",", ":")))


async def _run_swap(
    backend: NativeResearchBackend,
    store: TaskWorkspaceStore,
    source: NDArray[np.uint8],
    target: NDArray[np.uint8],
    source_face: DetectedFace,
    target_face: DetectedFace,
    detector_id: str,
    preset: QualityPreset,
) -> tuple[NDArray[np.uint8], float]:
    task_id = new_task_id()
    workspace = store.create(task_id)
    cv2.imwrite(str(workspace / "source.png"), source)
    cv2.imwrite(str(workspace / "target.png"), target)
    now = datetime.now(UTC)
    task = TaskRecord(
        task_id=task_id,
        actor_id="local-benchmark",
        status=TaskStatus.QUEUED,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        consent_version="local-benchmark-v1",
        consented_at=now,
        output_format=OutputFormat.PNG,
        watermark_enabled=False,
        quality_preset=preset,
        detector_id=detector_id,
        source_detection_id=source_face.detection_id,
        target_detection_id=target_face.detection_id,
        workflow_backend_id=NATIVE_RESEARCH_BACKEND_ID,
        swap_model_id=INSWAPPER_RESEARCH_MODEL_ID,
        research_model_license_accepted=True,
    )

    async def report_node(_: WorkflowNode) -> None:
        return None

    started = perf_counter()
    try:
        await backend.run(task, report_node)
        duration = perf_counter() - started
        output = decode_bgr_autorotated(store.result_path(task_id, OutputFormat.PNG))
        return output, duration
    finally:
        store.remove(task_id)


def _preset_metrics(
    target: NDArray[np.uint8],
    output: NDArray[np.uint8],
    target_face: DetectedFace,
    output_face: DetectedFace,
    source_embedding: NDArray[np.float32],
    output_embedding: NDArray[np.float32],
    duration: float,
) -> dict[str, object]:
    mask = face_blend_mask(target.shape[1], target.shape[0], target_face)
    core = mask >= 0.8
    target_lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype(np.float32)
    output_lab = cv2.cvtColor(output, cv2.COLOR_BGR2LAB).astype(np.float32)
    return {
        "source_identity_cosine": _round(cosine_similarity(source_embedding, output_embedding)),
        "landmark_nrmse": _round(landmark_nrmse(target_face, output_face)),
        "outside_face_change_ratio": _round(outside_face_change_ratio(target, output, target_face)),
        "core_target_lab_mae": _round(float(np.mean(np.abs(output_lab[core] - target_lab[core])))),
        "duration_seconds": _round(duration),
        "dimensions_preserved": output.shape == target.shape,
    }


def summarize(case_reports: list[dict[str, object]]) -> dict[str, object]:
    if not case_reports:
        return {"decision": "insufficient_successful_cases"}
    values: dict[str, dict[str, list[float]]] = {
        preset.value: {
            "identity": [],
            "landmarks": [],
            "outside": [],
            "colour": [],
            "duration": [],
        }
        for preset in QualityPreset
    }
    for case in case_reports:
        presets = cast(dict[str, dict[str, object]], case["presets"])
        for preset, metrics in presets.items():
            values[preset]["identity"].append(_metric_float(metrics, "source_identity_cosine"))
            values[preset]["landmarks"].append(_metric_float(metrics, "landmark_nrmse"))
            values[preset]["outside"].append(_metric_float(metrics, "outside_face_change_ratio"))
            values[preset]["colour"].append(_metric_float(metrics, "core_target_lab_mae"))
            values[preset]["duration"].append(_metric_float(metrics, "duration_seconds"))
    summary: dict[str, object] = {}
    for preset, samples_by_metric in values.items():
        preset_summary: dict[str, float] = {}
        for name, samples in samples_by_metric.items():
            preset_summary[f"median_{name}"] = _round(float(np.median(samples)))
            preset_summary[f"p95_{name}"] = _round(float(np.percentile(samples, 95)))
        summary[preset] = preset_summary
    all_durations = [
        duration for preset_values in values.values() for duration in preset_values["duration"]
    ]
    cold_start = max(all_durations)
    warm_durations = all_durations.copy()
    warm_durations.remove(cold_start)
    summary["performance"] = {
        "cold_start_seconds": _round(cold_start),
        "warm_task_median_seconds": _round(float(np.median(warm_durations))),
        "warm_task_p95_seconds": _round(float(np.percentile(warm_durations, 95))),
    }
    identity_delta = np.asarray(values["balanced"]["identity"]) - np.asarray(
        values["identity"]["identity"]
    )
    colour_delta = np.asarray(values["balanced"]["colour"]) - np.asarray(
        values["identity"]["colour"]
    )
    balanced_noninferior = float(np.median(identity_delta)) >= -0.01
    balanced_colour_better = float(np.median(colour_delta)) <= 0
    summary["balanced_minus_identity_median"] = {
        "identity_cosine": _round(float(np.median(identity_delta))),
        "core_target_lab_mae": _round(float(np.median(colour_delta))),
    }
    summary["decision"] = (
        "keep_balanced_default"
        if balanced_noninferior and balanced_colour_better
        else "revert_to_identity_default"
    )
    return summary


def _indexed_face(
    detector: FaceDetector,
    image: NDArray[np.uint8],
    one_based_index: int,
    case_id: str,
) -> DetectedFace:
    faces = detector.detect(image)
    if one_based_index < 1 or one_based_index > len(faces):
        raise ValueError(f"Face index is unavailable for {case_id}.")
    return faces[one_based_index - 1]


def load_cases(path: Path) -> tuple[BenchmarkCase, ...]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("benchmark case manifest is invalid")
    entries = value.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError("benchmark case manifest has no cases")
    cases: list[BenchmarkCase] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("benchmark case entry is invalid")
        case_id = entry.get("id")
        source = entry.get("source")
        target = entry.get("target")
        source_face = entry.get("source_face", 1)
        target_face = entry.get("target_face", 1)
        if (
            not isinstance(case_id, str)
            or not case_id.strip()
            or not isinstance(source, str)
            or not isinstance(target, str)
            or type(source_face) is not int
            or type(target_face) is not int
        ):
            raise ValueError("benchmark case fields are invalid")
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                source=_local_path(source),
                target=_local_path(target),
                source_face=source_face,
                target_face=target_face,
            )
        )
    return tuple(cases)


def _local_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("benchmark image must be an existing project-local file")
    return path


def _round(value: float) -> float:
    return round(value, 6)


def _metric_float(metrics: dict[str, object], key: str) -> float:
    value = metrics[key]
    if type(value) not in {int, float}:
        raise ValueError("benchmark metric is not numeric")
    return float(cast(int | float, value))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--confirm-image-authorization", action="store_true")
    parser.add_argument("--accept-research-license", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
