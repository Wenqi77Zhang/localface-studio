"""Compare pinned real models and sample sustained resource use on authorized local images."""

import argparse
import asyncio
import gc
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

from PIL import Image

from localface_studio.backends.native_research import (
    ALPHAFACE_RESEARCH_MODEL_ID,
    INSWAPPER_RESEARCH_MODEL_ID,
    NativeResearchBackend,
)
from localface_studio.backends.scrfd import ScrfdResearchFaceDetector
from localface_studio.benchmarking.face_swap_quality import cosine_similarity, match_output_face
from localface_studio.domain.tasks import (
    OutputFormat,
    QualityPreset,
    ResultVariant,
    TaskRecord,
    TaskStatus,
    new_task_id,
)
from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore
from scripts.benchmark_native_swap_quality import ArcFaceEvaluator, BenchmarkCase, load_cases

ROOT = Path(__file__).resolve().parents[1]


async def run_matrix(cases: tuple[BenchmarkCase, ...], output: Path, repeats: int) -> None:
    if not output.resolve().is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("private benchmark output must stay inside runtime")
    output.mkdir(parents=True, exist_ok=False)
    manifest = ROOT / "config/models.json"
    detector = ScrfdResearchFaceDetector.from_manifest(
        manifest, ROOT, research_license_accepted=True
    )
    evaluator = ArcFaceEvaluator(manifest)
    store = TaskWorkspaceStore(output / "work")
    backend = NativeResearchBackend(store, lambda _: detector, manifest, ROOT)
    rows: list[dict[str, object]] = []
    for model_id in (INSWAPPER_RESEARCH_MODEL_ID, ALPHAFACE_RESEARCH_MODEL_ID):
        for index, case in enumerate(cases):
            row = await run_case(case, model_id, backend, store, detector, evaluator, output)
            rows.append(row)
            print(
                json.dumps(
                    {
                        "model": model_id,
                        "case": index + 1,
                        "duration_ms": row["duration_ms"],
                        "status": row["status"],
                    }
                ),
                flush=True,
            )
    sustained: list[dict[str, object]] = []
    # One stable input, same backend, no process restart between tasks.
    for index in range(repeats):
        row = await run_case(
            cases[0],
            INSWAPPER_RESEARCH_MODEL_ID,
            backend,
            store,
            detector,
            evaluator,
            output,
            save_images=False,
        )
        sustained.append(row)
        gc.collect()
        print(
            json.dumps({"continuous_task": index + 1, "rss_end_mb": row.get("rss_end_mb")}),
            flush=True,
        )
    summaries: dict[str, object] = {}
    for model_id in (INSWAPPER_RESEARCH_MODEL_ID, ALPHAFACE_RESEARCH_MODEL_ID):
        group = [row for row in rows if row["model"] == model_id]
        similarities = [
            float(str(row["base_identity_cosine"]))
            for row in group
            if row.get("base_identity_cosine") is not None
        ]
        durations = [float(str(row["duration_ms"])) for row in group]
        summaries[model_id] = {
            "successful": sum(row["status"] == "ok" for row in group),
            "count": len(group),
            "identity_median": median(similarities) if similarities else None,
            "first_task_ms": durations[0],
            "hot_median_ms": median(durations[1:]) if len(durations) > 1 else None,
            "rss_peak_mb": max(float(str(row.get("rss_peak_mb", 0))) for row in group),
        }
    report = {
        "schema_version": 1,
        "measured_at": datetime.now(UTC).isoformat(),
        "summary": summaries,
        "cases": rows,
        "sustained": sustained,
        "limitations": [
            "One source identity; small sample; not a quality or fairness guarantee.",
            "Sequential models in one process; first-task timings are not comparable cold starts.",
            "VRAM is whole-device sampled use, not isolated process allocation.",
            "RSS includes cached models and allocator reserves; finite run cannot prove no leaks.",
        ],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summaries), flush=True)


async def run_case(
    case: BenchmarkCase,
    model_id: str,
    backend: NativeResearchBackend,
    store: TaskWorkspaceStore,
    detector: ScrfdResearchFaceDetector,
    evaluator: ArcFaceEvaluator,
    output: Path,
    *,
    save_images: bool = True,
) -> dict[str, object]:
    source = decode_bgr_autorotated(case.source)
    target = decode_bgr_autorotated(case.target)
    source_face = detector.detect(source)[case.source_face - 1]
    target_face = detector.detect(target)[case.target_face - 1]
    task_id = new_task_id()
    workspace = store.create(task_id)
    try:
        Image.fromarray(source[:, :, ::-1]).save(workspace / "source.png")
        Image.fromarray(target[:, :, ::-1]).save(workspace / "target.png")
        now = datetime.now(UTC)
        task = TaskRecord(
            task_id=task_id,
            actor_id="local-benchmark",
            status=TaskStatus.QUEUED,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=30),
            consent_version="local-authorized-benchmark",
            consented_at=now,
            output_format=OutputFormat.PNG,
            watermark_enabled=False,
            quality_preset=QualityPreset.BALANCED,
            detector_id=detector.detector_id,
            source_detection_id=source_face.detection_id,
            target_detection_id=target_face.detection_id,
            workflow_backend_id="native-research",
            swap_model_id=model_id,
            research_model_license_accepted=True,
        )
        await backend.run(task, lambda _: asyncio.sleep(0))
        metrics: dict[str, object] = json.loads(
            store.metrics_path(task_id).read_text(encoding="utf-8")
        )
        row: dict[str, object] = {
            "model": model_id,
            "case_id": case.case_id,
            "status": "ok",
            **metrics,
        }
        source_identity = evaluator.embedding(source, source_face)
        for variant in (ResultVariant.BASE, ResultVariant.ENHANCED):
            path = store.result_path(task_id, task.output_format, variant)
            generated = decode_bgr_autorotated(path)
            if generated.shape != target.shape:
                raise ValueError("output dimensions changed")
            try:
                match = match_output_face(target_face, detector.detect(generated))
            except ValueError:
                row[f"{variant.value}_identity_cosine"] = None
                row[f"{variant.value}_quality_warning"] = "output_face_not_matched"
            else:
                row[f"{variant.value}_identity_cosine"] = cosine_similarity(
                    source_identity, evaluator.embedding(generated, match)
                )
            if save_images:
                shutil.copyfile(path, output / f"{case.case_id}-{model_id}-{variant.value}.png")
        return row
    finally:
        store.remove(task_id)
        source.fill(0)
        target.fill(0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--confirm-image-authorization", action="store_true")
    parser.add_argument("--accept-research-license", action="store_true")
    args = parser.parse_args()
    if not args.confirm_image_authorization or not args.accept_research_license:
        raise SystemExit("Both image authorization and research license acceptance are required.")
    if not 0 <= args.repeats <= 100:
        raise SystemExit("repeats must be between 0 and 100")
    asyncio.run(run_matrix(load_cases(Path(args.cases)), Path(args.output), args.repeats))


if __name__ == "__main__":
    main()
