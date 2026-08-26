"""Optional ComfyUI adapter workflow, output, and cleanup tests."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from localface_studio.backends.comfyui import (
    ComfyOutputReference,
    ComfyUiBackend,
    _load_workflow,
)
from localface_studio.backends.result_export import read_result_metadata
from localface_studio.domain.tasks import OutputFormat, TaskRecord, TaskStatus, WorkflowNode
from localface_studio.infrastructure.config import Settings
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore


def _task() -> TaskRecord:
    now = datetime.now(UTC)
    return TaskRecord(
        task_id="comfyui-adapter-task-00000000001",
        actor_id="private",
        status=TaskStatus.RUNNING,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        consent_version="test",
        consented_at=now,
        output_format=OutputFormat.PNG,
        watermark_enabled=True,
        workflow_backend_id="comfyui",
        swap_model_id="comfyui-user-workflow",
    )


def _workflow(path: Path, *, license_reviewed: bool = True) -> None:
    payload = {
        "schema_version": 1,
        "license_reviewed": license_reviewed,
        "network_access_required": False,
        "result_node_id": "3",
        "allowed_node_classes": ["LoadImage", "FaceSwap", "SaveImage"],
        "prompt": {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": "__LOCALFACE_SOURCE_IMAGE__"},
            },
            "2": {
                "class_type": "LoadImage",
                "inputs": {"image": "__LOCALFACE_TARGET_IMAGE__"},
            },
            "swap": {
                "class_type": "FaceSwap",
                "inputs": {"source": ["1", 0], "target": ["2", 0]},
            },
            "3": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "__LOCALFACE_OUTPUT_PREFIX__",
                    "images": ["swap", 0],
                },
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class FakeComfyClient:
    def __init__(self, input_root: Path, encoded: bytes) -> None:
        self.input_root = input_root
        self.encoded = encoded
        self.cancelled: list[str] = []
        self.deleted: list[str] = []
        self.submitted: dict[str, object] | None = None

    async def health(self) -> None:
        return None

    async def upload_image(self, path: Path, *, name: str, subfolder: str) -> str:
        destination = self.input_root / Path(*subfolder.split("/"))
        destination.mkdir(parents=True, exist_ok=True)
        (destination / name).write_bytes(path.read_bytes())
        return f"{subfolder}/{name}"

    async def submit(self, prompt: dict[str, object]) -> str:
        self.submitted = prompt
        return "prompt-id"

    async def history(self, prompt_id: str) -> dict[str, object] | None:
        assert prompt_id == "prompt-id"
        return {
            "outputs": {
                "3": {
                    "images": [
                        {
                            "filename": "result_00001_.png",
                            "subfolder": "localface/comfyui-adapter-task-00000000001",
                            "type": "output",
                        }
                    ]
                }
            }
        }

    async def download(self, reference: ComfyOutputReference) -> bytes:
        assert reference.filename == "result_00001_.png"
        return self.encoded

    async def cancel(self, prompt_id: str) -> None:
        self.cancelled.append(prompt_id)

    async def delete_history(self, prompt_id: str) -> None:
        self.deleted.append(prompt_id)


def test_comfyui_backend_publishes_local_result_and_cleans_exchange(tmp_path: Path) -> None:
    task = _task()
    store = TaskWorkspaceStore(tmp_path / "tasks")
    workspace = store.create(task.task_id)
    Image.new("RGB", (16, 16), "red").save(workspace / "source.png")
    Image.new("RGB", (24, 18), "blue").save(workspace / "target.png")
    encoded_stream = BytesIO()
    Image.new("RGB", (24, 18), "green").save(encoded_stream, format="PNG")
    workflow = tmp_path / "workflow.json"
    _workflow(workflow)
    input_root = tmp_path / "comfy-input"
    output_root = tmp_path / "comfy-output"
    input_root.mkdir()
    output_task = output_root / "localface" / task.task_id
    output_task.mkdir(parents=True)
    (output_task / "result_00001_.png").write_bytes(encoded_stream.getvalue())
    client = FakeComfyClient(input_root, encoded_stream.getvalue())
    settings = Settings(
        workflow_backend="comfyui",
        comfyui_workflow_path=workflow,
        comfyui_input_directory=input_root,
        comfyui_output_directory=output_root,
    )
    backend = ComfyUiBackend(store, settings, client=client)
    nodes: list[WorkflowNode] = []

    asyncio.run(backend.run(task, lambda node: _append(nodes, node)))

    with Image.open(store.result_path(task.task_id, OutputFormat.PNG)) as result:
        metadata = read_result_metadata(result, OutputFormat.PNG)
    assert metadata["backend"] == "comfyui"
    assert metadata["ai_edited"] is True
    assert client.submitted is not None
    assert client.deleted == ["prompt-id"]
    assert not (input_root / "localface" / task.task_id).exists()
    assert not output_task.exists()
    assert nodes == [
        WorkflowNode.VALIDATE,
        WorkflowNode.PREPARE,
        WorkflowNode.SWAP,
        WorkflowNode.INSPECT,
        WorkflowNode.EXPORT,
    ]


def test_workflow_rejects_unreviewed_license_or_undeclared_node(tmp_path: Path) -> None:
    path = tmp_path / "workflow.json"
    _workflow(path, license_reviewed=False)
    with pytest.raises(ValueError, match="license or network"):
        _load_workflow(path)

    _workflow(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["prompt"]["swap"]["class_type"] = "UnreviewedNode"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="undeclared node"):
        _load_workflow(path)


async def _append(nodes: list[WorkflowNode], node: WorkflowNode) -> None:
    nodes.append(node)
