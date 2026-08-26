"""Optional loopback-only ComfyUI workflow adapter with fail-closed cleanup."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError

from localface_studio import __version__
from localface_studio.application.task_queue import NodeReporter, WorkflowExecutionError
from localface_studio.backends.result_export import draw_ai_watermark, save_result
from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import TaskRecord, WorkflowNode
from localface_studio.infrastructure.config import Settings
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

COMFYUI_BACKEND_ID = "comfyui"
COMFYUI_WORKFLOW_MODEL_ID = "comfyui-user-workflow"
_SOURCE_PLACEHOLDER = "__LOCALFACE_SOURCE_IMAGE__"
_TARGET_PLACEHOLDER = "__LOCALFACE_TARGET_IMAGE__"
_OUTPUT_PLACEHOLDER = "__LOCALFACE_OUTPUT_PREFIX__"
_MAXIMUM_RESULT_BYTES = 25 * 1024 * 1024


class ComfyUiProtocolError(RuntimeError):
    """ComfyUI returned an unavailable, malformed, or unsafe response."""


@dataclass(frozen=True, slots=True)
class ComfyOutputReference:
    filename: str
    subfolder: str
    folder_type: str


class ComfyUiClient(Protocol):
    async def health(self) -> None: ...

    async def upload_image(self, path: Path, *, name: str, subfolder: str) -> str: ...

    async def submit(self, prompt: dict[str, object]) -> str: ...

    async def history(self, prompt_id: str) -> dict[str, object] | None: ...

    async def download(self, reference: ComfyOutputReference) -> bytes: ...

    async def cancel(self, prompt_id: str) -> None: ...

    async def delete_history(self, prompt_id: str) -> None: ...


class HttpComfyUiClient:
    """Small legacy ComfyUI HTTP client based on the official stable routes."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 15.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> None:
        response = await self._client.get("/system_stats")
        if response.status_code != 200 or not isinstance(_json(response), dict):
            raise ComfyUiProtocolError("ComfyUI health response is invalid")

    async def upload_image(self, path: Path, *, name: str, subfolder: str) -> str:
        with path.open("rb") as stream:
            response = await self._client.post(
                "/upload/image",
                data={"subfolder": subfolder, "type": "input", "overwrite": "true"},
                files={"image": (name, stream, "application/octet-stream")},
            )
        payload = _json_object(response)
        remote_name = payload.get("name")
        remote_subfolder = payload.get("subfolder")
        if response.status_code != 200 or remote_name != name or remote_subfolder != subfolder:
            raise ComfyUiProtocolError("ComfyUI upload response is invalid")
        return f"{subfolder}/{name}"

    async def submit(self, prompt: dict[str, object]) -> str:
        response = await self._client.post(
            "/prompt",
            json={"prompt": prompt, "client_id": uuid4().hex},
        )
        payload = _json_object(response)
        prompt_id = payload.get("prompt_id")
        if response.status_code != 200 or not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUiProtocolError("ComfyUI prompt response is invalid")
        if payload.get("node_errors") not in (None, {}):
            raise ComfyUiProtocolError("ComfyUI rejected one or more workflow nodes")
        return prompt_id

    async def history(self, prompt_id: str) -> dict[str, object] | None:
        response = await self._client.get(f"/history/{prompt_id}")
        payload = _json_object(response)
        entry = payload.get(prompt_id)
        if response.status_code != 200:
            raise ComfyUiProtocolError("ComfyUI history request failed")
        if entry is None:
            return None
        if not isinstance(entry, dict):
            raise ComfyUiProtocolError("ComfyUI history response is invalid")
        return cast(dict[str, object], entry)

    async def download(self, reference: ComfyOutputReference) -> bytes:
        chunks = bytearray()
        async with self._client.stream(
            "GET",
            "/view",
            params={
                "filename": reference.filename,
                "subfolder": reference.subfolder,
                "type": reference.folder_type,
            },
        ) as response:
            if response.status_code != 200:
                raise ComfyUiProtocolError("ComfyUI result response is invalid")
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > _MAXIMUM_RESULT_BYTES:
                    raise ComfyUiProtocolError("ComfyUI result is too large")
        return bytes(chunks)

    async def cancel(self, prompt_id: str) -> None:
        await self._client.post("/queue", json={"delete": [prompt_id]})

    async def delete_history(self, prompt_id: str) -> None:
        await self._client.post("/history", json={"delete": [prompt_id]})


class ComfyUiBackend:
    """Render one audited API workflow without importing ComfyUI code."""

    def __init__(
        self,
        workspaces: TaskWorkspaceStore,
        settings: Settings,
        *,
        client: ComfyUiClient | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._settings = settings
        self._client = client

    def capabilities(self) -> dict[str, object]:
        configured = (
            self._settings.comfyui_workflow_path.is_file()
            and self._settings.comfyui_input_directory is not None
            and self._settings.comfyui_input_directory.is_dir()
            and self._settings.comfyui_output_directory is not None
            and self._settings.comfyui_output_directory.is_dir()
        )
        return {
            "workflow_backend": COMFYUI_BACKEND_ID,
            "model_files_present": configured,
            "model_integrity_verified": False,
            "runtime_loaded": False,
            "execution_provider": "not_loaded",
            "research_only": False,
        }

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        await report_node(WorkflowNode.VALIDATE)
        package = _load_workflow(self._settings.comfyui_workflow_path)
        input_root, output_root = self._exchange_roots()
        source = self._workspaces.input_path(task.task_id, ImageRole.SOURCE)
        target = self._workspaces.input_path(task.task_id, ImageRole.TARGET)
        exchange_subfolder = f"localface/{task.task_id}"
        client = self._client or HttpComfyUiClient(self._settings.comfyui_url)
        owns_client = self._client is None
        prompt_id: str | None = None
        try:
            await client.health()
            await report_node(WorkflowNode.PREPARE)
            source_name = await client.upload_image(
                source, name=f"source{source.suffix}", subfolder=exchange_subfolder
            )
            target_name = await client.upload_image(
                target, name=f"target{target.suffix}", subfolder=exchange_subfolder
            )
            prompt = _render_prompt(
                package.prompt,
                source_name=source_name,
                target_name=target_name,
                output_prefix=f"{exchange_subfolder}/result",
            )
            await report_node(WorkflowNode.SWAP)
            prompt_id = await client.submit(prompt)
            entry = await _wait_for_history(client, prompt_id)
            reference = _output_reference(entry, package.result_node_id, exchange_subfolder)
            encoded = await client.download(reference)
            await report_node(WorkflowNode.INSPECT)
            self._publish_result(task, target, encoded)
            await report_node(WorkflowNode.EXPORT)
        except asyncio.CancelledError:
            if prompt_id is not None:
                await _best_effort_cancel(client, prompt_id)
            raise
        except (ComfyUiProtocolError, httpx.HTTPError, OSError, ValueError) as error:
            raise WorkflowExecutionError("comfyui_workflow_failed") from error
        finally:
            if prompt_id is not None:
                await _best_effort_history_delete(client, prompt_id)
            _remove_exchange_directory(input_root, exchange_subfolder)
            _remove_exchange_directory(output_root, exchange_subfolder)
            if owns_client:
                await cast(HttpComfyUiClient, client).close()

    def _exchange_roots(self) -> tuple[Path, Path]:
        input_root = self._settings.comfyui_input_directory
        output_root = self._settings.comfyui_output_directory
        if input_root is None or output_root is None:
            raise ValueError("ComfyUI exchange directories are not configured")
        roots = (input_root.resolve(), output_root.resolve())
        if not all(root.is_dir() for root in roots):
            raise ValueError("ComfyUI exchange directories are unavailable")
        return roots

    def _publish_result(self, task: TaskRecord, target_path: Path, encoded: bytes) -> None:
        if not encoded or len(encoded) > _MAXIMUM_RESULT_BYTES:
            raise ComfyUiProtocolError("ComfyUI result size is invalid")
        staging_download = self._workspaces.result_staging_path(task.task_id)
        staging_download.write_bytes(encoded)
        try:
            with Image.open(target_path) as target:
                target_size = target.size
            with Image.open(staging_download) as generated:
                generated.load()
                if generated.size != target_size:
                    raise ComfyUiProtocolError("ComfyUI changed the target dimensions")
                result = generated.convert("RGBA")
        except (UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise ComfyUiProtocolError("ComfyUI returned a non-image result") from error
        finally:
            staging_download.unlink(missing_ok=True)
        if task.watermark_enabled:
            draw_ai_watermark(result)
        metadata: dict[str, object] = {
            "app": "LocalFace Studio",
            "app_version": __version__,
            "ai_edited": True,
            "backend": COMFYUI_BACKEND_ID,
            "created_at": datetime.now(UTC).isoformat(),
            "simulation": False,
            "detector_id": task.detector_id,
            "swap_model_id": COMFYUI_WORKFLOW_MODEL_ID,
            "visible_watermark": task.watermark_enabled,
            "jpeg_quality": task.jpeg_quality,
            "quality_preset": task.quality_preset.value,
        }
        staging = self._workspaces.result_staging_path(task.task_id)
        destination = self._workspaces.result_path(task.task_id, task.output_format)
        try:
            save_result(
                result,
                staging,
                task.output_format,
                metadata,
                jpeg_quality=task.jpeg_quality,
            )
            staging.replace(destination)
        finally:
            staging.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class _WorkflowPackage:
    prompt: dict[str, object]
    result_node_id: str


def _load_workflow(path: Path) -> _WorkflowPackage:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("ComfyUI workflow package is invalid")
    prompt = payload.get("prompt")
    result_node_id = payload.get("result_node_id")
    allowed = payload.get("allowed_node_classes")
    if not isinstance(prompt, dict) or not isinstance(result_node_id, str):
        raise ValueError("ComfyUI workflow package fields are invalid")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(x, str) for x in allowed):
        raise ValueError("ComfyUI node allowlist is invalid")
    if (
        payload.get("license_reviewed") is not True
        or payload.get("network_access_required") is not False
    ):
        raise ValueError("ComfyUI workflow license or network declaration is unsafe")
    actual = [
        node.get("class_type")
        for node in prompt.values()
        if isinstance(node, dict) and isinstance(node.get("class_type"), str)
    ]
    if len(actual) != len(prompt) or not set(actual).issubset(set(allowed)):
        raise ValueError("ComfyUI workflow contains an undeclared node class")
    return _WorkflowPackage(cast(dict[str, object], prompt), result_node_id)


def _render_prompt(
    prompt: Mapping[str, object],
    *,
    source_name: str,
    target_name: str,
    output_prefix: str,
) -> dict[str, object]:
    serialized = json.dumps(prompt, separators=(",", ":"))
    replacements = {
        _SOURCE_PLACEHOLDER: source_name,
        _TARGET_PLACEHOLDER: target_name,
        _OUTPUT_PLACEHOLDER: output_prefix,
    }
    for placeholder, value in replacements.items():
        if serialized.count(f'"{placeholder}"') != 1:
            raise ValueError(f"ComfyUI workflow must contain one {placeholder}")
        serialized = serialized.replace(f'"{placeholder}"', json.dumps(value))
    rendered: object = json.loads(serialized)
    if not isinstance(rendered, dict):
        raise ValueError("rendered ComfyUI prompt is invalid")
    return cast(dict[str, object], rendered)


async def _wait_for_history(
    client: ComfyUiClient,
    prompt_id: str,
    *,
    attempts: int = 600,
) -> dict[str, object]:
    for _ in range(attempts):
        entry = await client.history(prompt_id)
        if entry is not None:
            return entry
        await asyncio.sleep(0.5)
    raise ComfyUiProtocolError("ComfyUI workflow timed out")


def _output_reference(
    entry: dict[str, object],
    result_node_id: str,
    expected_subfolder: str,
) -> ComfyOutputReference:
    outputs = entry.get("outputs")
    node = outputs.get(result_node_id) if isinstance(outputs, dict) else None
    images = node.get("images") if isinstance(node, dict) else None
    value = images[0] if isinstance(images, list) and images else None
    if not isinstance(value, dict):
        raise ComfyUiProtocolError("ComfyUI result node did not return an image")
    filename, subfolder, folder_type = (
        value.get("filename"),
        value.get("subfolder"),
        value.get("type"),
    )
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not isinstance(subfolder, str)
        or subfolder.replace("\\", "/") != expected_subfolder
        or folder_type != "output"
    ):
        raise ComfyUiProtocolError("ComfyUI result reference escaped its task directory")
    return ComfyOutputReference(filename, subfolder, folder_type)


def _remove_exchange_directory(root: Path, subfolder: str) -> None:
    candidate = (root / Path(*subfolder.split("/"))).resolve()
    if candidate.is_relative_to(root) and candidate.parent.name == "localface":
        shutil.rmtree(candidate, ignore_errors=True)


async def _best_effort_cancel(client: ComfyUiClient, prompt_id: str) -> None:
    with suppress(Exception):
        await client.cancel(prompt_id)


async def _best_effort_history_delete(client: ComfyUiClient, prompt_id: str) -> None:
    with suppress(Exception):
        await client.delete_history(prompt_id)


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as error:
        raise ComfyUiProtocolError("ComfyUI returned invalid JSON") from error


def _json_object(response: httpx.Response) -> dict[str, object]:
    payload = _json(response)
    if not isinstance(payload, dict):
        raise ComfyUiProtocolError("ComfyUI returned an invalid object")
    return cast(dict[str, object], payload)
