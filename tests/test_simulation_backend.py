"""No-model simulation output, disclosure, and metadata tests."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image

from localface_studio.backends.simulation import (
    METADATA_KEY,
    SIMULATION_STATEMENT,
    SimulationBackend,
)
from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import (
    OutputFormat,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
)
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore


def make_task(output_format: OutputFormat, *, watermark: bool) -> TaskRecord:
    now = datetime.now(UTC)
    return TaskRecord(
        task_id="simulation-task-identifier-000001",
        actor_id="private-actor",
        status=TaskStatus.RUNNING,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        consent_version="2026-07-23-v1",
        consented_at=now,
        output_format=output_format,
        watermark_enabled=watermark,
    )


def prepare_inputs(store: TaskWorkspaceStore, task: TaskRecord) -> None:
    workspace = store.create(task.task_id)
    Image.new("RGB", (320, 240), (220, 20, 40)).save(workspace / "source.png")
    target = Image.new("RGB", (640, 360), (30, 100, 180))
    for x in range(0, 640, 40):
        for y in range(0, 360, 40):
            if (x + y) // 40 % 2:
                target.paste((40, 180, 90), (x, y, x + 40, y + 40))
    target.save(workspace / "target.png")


def read_metadata(path: Path, output_format: OutputFormat) -> dict[str, object]:
    with Image.open(path) as image:
        raw = (
            image.info[METADATA_KEY] if output_format is OutputFormat.PNG else image.getexif()[270]
        )
    assert isinstance(raw, str)
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


def test_simulation_exports_disclosed_png_and_jpeg_without_sensitive_metadata(
    tmp_path: Path,
) -> None:
    async def run_case(output_format: OutputFormat, watermark: bool) -> None:
        store = TaskWorkspaceStore(tmp_path / f"{output_format}-{watermark}")
        task = make_task(output_format, watermark=watermark)
        prepare_inputs(store, task)
        nodes: list[WorkflowNode] = []

        async def report(node: WorkflowNode) -> None:
            nodes.append(node)

        await SimulationBackend(store).run(task, report)

        result_path = store.result_path(task.task_id, output_format)
        with Image.open(store.input_path(task.task_id, role=ImageRole.TARGET)) as target:
            target_pixels = target.convert("RGB").tobytes()
            target_size = target.size
        with Image.open(result_path) as result:
            result.load()
            result_pixels = result.convert("RGB").tobytes()
            assert result.size == target_size
        metadata = read_metadata(result_path, output_format)
        serialized = json.dumps(metadata, ensure_ascii=False)
        assert result_pixels != target_pixels
        assert metadata["simulation"] is True
        assert metadata["ai_edited"] is True
        assert metadata["backend"] == "simulation"
        assert metadata["statement"] == SIMULATION_STATEMENT
        assert metadata["visible_watermark"] is watermark
        assert "private-actor" not in serialized
        assert str(tmp_path) not in serialized
        assert nodes == list(WorkflowNode)

    asyncio.run(run_case(OutputFormat.PNG, True))
    asyncio.run(run_case(OutputFormat.JPEG, False))


def test_simulation_reports_missing_input_with_stable_error(tmp_path: Path) -> None:
    from localface_studio.application.task_queue import WorkflowExecutionError

    async def scenario() -> None:
        store = TaskWorkspaceStore(tmp_path)
        task = make_task(OutputFormat.PNG, watermark=True)
        store.create(task.task_id)

        async def report(node: WorkflowNode) -> None:
            assert node is WorkflowNode.VALIDATE

        try:
            await SimulationBackend(store).run(task, report)
        except WorkflowExecutionError as error:
            assert error.error_code == "simulation_input_missing"
        else:
            raise AssertionError("missing inputs must fail")

    asyncio.run(scenario())
