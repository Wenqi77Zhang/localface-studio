"""Honest no-model backend used to validate the product workflow."""

import asyncio
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin, UnidentifiedImageError

from localface_studio import __version__
from localface_studio.application.task_queue import (
    NodeReporter,
    WorkflowExecutionError,
)
from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import OutputFormat, TaskRecord, WorkflowNode
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore

SIMULATION_STATEMENT = "SIMULATION—非真实换脸结果"
SIMULATION_BANNER_FALLBACK = "SIMULATION - NOT A FACE SWAP"
AI_WATERMARK = "AI EDITED - LocalFace Studio"
METADATA_KEY = "LocalFaceStudio"


class SimulationBackend:
    """Copy the target image with unambiguous simulation disclosure."""

    def __init__(self, workspaces: TaskWorkspaceStore) -> None:
        self._workspaces = workspaces

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        await report_node(WorkflowNode.VALIDATE)
        try:
            source_path = self._workspaces.input_path(task.task_id, ImageRole.SOURCE)
            target_path = self._workspaces.input_path(task.task_id, ImageRole.TARGET)
        except FileNotFoundError as error:
            raise WorkflowExecutionError("simulation_input_missing") from error

        await report_node(WorkflowNode.PREPARE)
        await report_node(WorkflowNode.SIMULATE)
        try:
            await asyncio.to_thread(self._render, task, source_path, target_path)
        except (OSError, ValueError, UnidentifiedImageError) as error:
            raise WorkflowExecutionError("simulation_render_failed") from error

        await report_node(WorkflowNode.INSPECT)
        try:
            await asyncio.to_thread(self._inspect, task, target_path)
        except (OSError, ValueError, UnidentifiedImageError) as error:
            raise WorkflowExecutionError("simulation_output_invalid") from error
        await report_node(WorkflowNode.EXPORT)

    def _render(self, task: TaskRecord, source_path: Path, target_path: Path) -> None:
        # Opening the source confirms the complete pair is still readable. Its pixels
        # are deliberately never used by this phase-2 non-model backend.
        with Image.open(source_path) as source:
            source.load()
        with Image.open(target_path) as target:
            target.load()
            result = target.convert("RGBA")

        self._draw_disclosure(result, task.watermark_enabled)
        metadata = self._metadata(task)
        staging_path = self._workspaces.result_staging_path(task.task_id)
        result_path = self._workspaces.result_path(task.task_id, task.output_format)
        if staging_path.exists():
            staging_path.unlink()
        try:
            self._save(result, staging_path, task.output_format, metadata)
            staging_path.replace(result_path)
        finally:
            if staging_path.exists():
                staging_path.unlink()

    @staticmethod
    def _draw_disclosure(image: Image.Image, watermark_enabled: bool) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        font_size = max(12, min(30, width // 24, height // 10))
        font, supports_chinese = _load_disclosure_font(font_size)
        text = SIMULATION_STATEMENT if supports_chinese else SIMULATION_BANNER_FALLBACK
        lines = [text]
        if watermark_enabled:
            lines.append(AI_WATERMARK)
        padding = max(4, font_size // 3)
        spacing = max(2, font_size // 5)
        boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        text_height = sum(box[3] - box[1] for box in boxes) + spacing * (len(lines) - 1)
        banner_height = min(height, text_height + 2 * padding)
        draw.rectangle((0, height - banner_height, width, height), fill=(0, 0, 0, 210))
        y = height - banner_height + padding
        for line, box in zip(lines, boxes, strict=True):
            line_width = box[2] - box[0]
            x = max(padding, (width - line_width) // 2)
            draw.text((x, y), line, font=font, fill=(255, 220, 60, 255))
            y += box[3] - box[1] + spacing

    @staticmethod
    def _metadata(task: TaskRecord) -> dict[str, object]:
        return {
            "app": "LocalFace Studio",
            "app_version": __version__,
            "ai_edited": True,
            "backend": "simulation",
            "created_at": datetime.now(UTC).isoformat(),
            "simulation": True,
            "statement": SIMULATION_STATEMENT,
            "visible_watermark": task.watermark_enabled,
        }

    @staticmethod
    def _save(
        image: Image.Image,
        destination: Path,
        output_format: OutputFormat,
        metadata: dict[str, object],
    ) -> None:
        if output_format is OutputFormat.PNG:
            serialized = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text(METADATA_KEY, serialized)
            image.save(destination, format="PNG", pnginfo=png_info)
            return
        # EXIF ImageDescription is commonly constrained to ASCII. JSON Unicode
        # escapes preserve the original statement without lossy substitution.
        serialized = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
        exif = Image.Exif()
        exif[270] = serialized
        exif[305] = "LocalFace Studio"
        image.convert("RGB").save(destination, format="JPEG", quality=95, exif=exif)

    def _inspect(self, task: TaskRecord, target_path: Path) -> None:
        result_path = self._workspaces.result_path(task.task_id, task.output_format)
        with Image.open(target_path) as target:
            target_size = target.size
        with Image.open(result_path) as result:
            result.load()
            if result.size != target_size:
                raise ValueError("simulation output dimensions changed")
            metadata = _read_metadata(result, task.output_format)
        if metadata.get("simulation") is not True or metadata.get("ai_edited") is not True:
            raise ValueError("required simulation metadata is missing")


def _font_candidates() -> Iterable[tuple[Path, bool]]:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    yield windows / "msyh.ttc", True
    yield windows / "simhei.ttf", True
    yield Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), True
    yield Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), False


def _load_disclosure_font(size: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, bool]:
    for candidate, supports_chinese in _font_candidates():
        if candidate.is_file():
            try:
                return ImageFont.truetype(candidate, size=size), supports_chinese
            except OSError:
                continue
    return ImageFont.load_default(size=size), False


def _read_metadata(image: Image.Image, output_format: OutputFormat) -> dict[str, object]:
    raw = (
        image.info.get(METADATA_KEY)
        if output_format is OutputFormat.PNG
        else image.getexif().get(270)
    )
    if not isinstance(raw, str):
        raise ValueError("result metadata is absent")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("result metadata is not an object")
    return value
