"""Run one consent-gated native swap without starting the web application."""

import argparse
import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from localface_studio.application.face_detection import FaceDetector
from localface_studio.backends.native_research import (
    INSWAPPER_RESEARCH_MODEL_ID,
    NATIVE_RESEARCH_BACKEND_ID,
    NativeResearchBackend,
)
from localface_studio.backends.scrfd import (
    SCRFD_RESEARCH_MODEL_ID,
    ScrfdResearchFaceDetector,
)
from localface_studio.backends.yunet import YUNET_MODEL_ID, YuNetFaceDetector
from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import (
    OutputFormat,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
    new_task_id,
)
from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore


def main() -> None:
    args = parse_args()
    if args.accept_research_license is not True:
        raise SystemExit("Pass --accept-research-license to use restricted pretrained weights.")
    root = Path(__file__).resolve().parents[1]
    manifest = root / "config" / "models.json"
    store = TaskWorkspaceStore(root / ".tools" / "native-smoke")
    task_id = new_task_id()
    workspace = store.create(task_id)
    source_path = _copy_input(Path(args.source), workspace, ImageRole.SOURCE)
    target_path = _copy_input(Path(args.target), workspace, ImageRole.TARGET)
    detector = _detector(args.detector_id, manifest, root)
    source_faces = detector.detect(decode_bgr_autorotated(source_path))
    target_faces = detector.detect(decode_bgr_autorotated(target_path))
    if not source_faces or not target_faces:
        store.remove(task_id)
        raise SystemExit("A face was not detected in one or both images.")
    source_face = source_faces[args.source_face - 1]
    target_face = target_faces[args.target_face - 1]
    now = datetime.now(UTC)
    output = Path(args.output)
    output_format = (
        OutputFormat.JPEG if output.suffix.casefold() in {".jpg", ".jpeg"} else OutputFormat.PNG
    )
    task = TaskRecord(
        task_id=task_id,
        actor_id="native-smoke",
        status=TaskStatus.QUEUED,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        consent_version="native-smoke-v1",
        consented_at=now,
        output_format=output_format,
        watermark_enabled=args.watermark,
        detector_id=detector.detector_id,
        source_detection_id=source_face.detection_id,
        target_detection_id=target_face.detection_id,
        workflow_backend_id=NATIVE_RESEARCH_BACKEND_ID,
        swap_model_id=INSWAPPER_RESEARCH_MODEL_ID,
        research_model_license_accepted=True,
    )

    async def run() -> None:
        async def report_node(_: WorkflowNode) -> None:
            return None

        backend = NativeResearchBackend(store, lambda _: detector, manifest, root)
        await backend.run(task, report_node)

    try:
        asyncio.run(run())
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store.result_path(task_id, output_format), output)
        print(f"Native swap completed with {detector.detector_id}: {output.name}")
    finally:
        store.remove(task_id)


def _detector(detector_id: str, manifest: Path, root: Path) -> FaceDetector:
    if detector_id == SCRFD_RESEARCH_MODEL_ID:
        return ScrfdResearchFaceDetector.from_manifest(
            manifest,
            root,
            research_license_accepted=True,
        )
    if detector_id == YUNET_MODEL_ID:
        return YuNetFaceDetector.from_manifest(manifest, root)
    raise SystemExit("Unsupported detector ID.")


def _copy_input(source: Path, workspace: Path, role: ImageRole) -> Path:
    if not source.is_file():
        raise SystemExit(f"{role.value} image is unavailable.")
    suffix = source.suffix.casefold()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise SystemExit(f"{role.value} image has an unsupported extension.")
    destination = workspace / f"{role.value}{'.jpg' if suffix == '.jpeg' else suffix}"
    shutil.copyfile(source, destination)
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--detector-id",
        choices=[YUNET_MODEL_ID, SCRFD_RESEARCH_MODEL_ID],
        default=YUNET_MODEL_ID,
    )
    parser.add_argument("--source-face", type=int, default=1)
    parser.add_argument("--target-face", type=int, default=1)
    parser.add_argument("--watermark", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--accept-research-license", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
