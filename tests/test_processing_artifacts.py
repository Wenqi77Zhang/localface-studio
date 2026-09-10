"""Real orchestration with injected model boundaries, never third-party weights in CI."""

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from localface_studio.application.face_processing import SwapOutput
from localface_studio.application.task_queue import WorkflowExecutionError
from localface_studio.backends.alphaface import paste_aligned_face
from localface_studio.backends.native_research import NativeResearchBackend
from localface_studio.backends.result_export import read_result_metadata
from localface_studio.domain.tasks import OutputFormat, QualityPreset, ResultVariant, WorkflowNode
from tests.test_native_research_backend import FakeDetector, _face, _prepare_store, _task


class SelectedSwapper:
    def swap(
        self, source: np.ndarray, target: np.ndarray, source_face: Any, target_face: Any
    ) -> SwapOutput:
        result = target.copy()
        result[3:9, 3:9] = (8, 16, 24)
        return SwapOutput(result, ("CPUExecutionProvider",))

    def capabilities(self) -> dict[str, object]:
        return {"model_files_present": True}


class IndependentEnhancer:
    enhancer_id = "test-bounded-enhancer"

    def enhance(self, target: np.ndarray, base: np.ndarray, target_face: Any) -> np.ndarray:
        result = base.copy()
        result[3:9, 3:9] = (22, 33, 44)
        return result


@pytest.mark.parametrize("output_format", [OutputFormat.PNG, OutputFormat.JPEG])
@pytest.mark.parametrize("preset", [QualityPreset.IDENTITY, QualityPreset.BALANCED])
@pytest.mark.parametrize("watermark", [True, False])
def test_artifacts_are_independent_disclosed_and_optional(
    tmp_path: Path,
    output_format: OutputFormat,
    preset: QualityPreset,
    watermark: bool,
) -> None:
    face = _face(2)
    task = _task(
        face, face, quality_preset=preset, output_format=output_format, watermark_enabled=watermark
    )
    store = _prepare_store(tmp_path, task)
    backend = NativeResearchBackend(
        store,
        lambda _: FakeDetector((face,)),
        tmp_path / "models.json",
        tmp_path,
        swapper=SelectedSwapper(),
        enhancer=IndependentEnhancer(),
    )
    nodes = []

    async def report(node: WorkflowNode) -> None:
        nodes.append(node)

    asyncio.run(backend.run(task, report))
    variants = store.result_variants(task.task_id, output_format)
    assert variants == (
        [ResultVariant.BASE, ResultVariant.ENHANCED]
        if preset is QualityPreset.BALANCED
        else [ResultVariant.BASE]
    )
    for variant in variants:
        with Image.open(store.result_path(task.task_id, output_format, variant)) as image:
            assert image.size == (18, 16)
            metadata = read_result_metadata(image, output_format)
        assert metadata["result_variant"] == variant.value
        assert metadata["simulation"] is False
        assert metadata["visible_watermark"] is watermark
        assert metadata["ai_edited"] is True
    assert (WorkflowNode.ENHANCE in nodes) is (preset is QualityPreset.BALANCED)
    assert not (tmp_path / "tasks" / task.task_id / "source.part").exists()
    assert not (tmp_path / "tasks" / task.task_id / "result.part").exists()
    metrics = json.loads(store.metrics_path(task.task_id).read_text(encoding="utf-8"))
    assert metrics["duration_ms"] > 0
    assert metrics["rss_peak_mb"] >= metrics["rss_start_mb"]
    if preset is QualityPreset.BALANCED and not watermark:
        assert store.result_path(task.task_id, output_format, ResultVariant.BASE).read_bytes() != (
            store.result_path(task.task_id, output_format, ResultVariant.ENHANCED).read_bytes()
        )


@pytest.mark.parametrize("broken", ["noop", "shape"])
def test_noop_and_invalid_model_outputs_never_publish_success(tmp_path: Path, broken: str) -> None:
    class BrokenSwapper(SelectedSwapper):
        def swap(
            self, source: np.ndarray, target: np.ndarray, source_face: Any, target_face: Any
        ) -> SwapOutput:
            result = target.copy() if broken == "noop" else target[:2].copy()
            return SwapOutput(result, ("CPUExecutionProvider",))

    face = _face(2)
    task = _task(face, face)
    store = _prepare_store(tmp_path, task)
    backend = NativeResearchBackend(
        store,
        lambda _: FakeDetector((face,)),
        tmp_path / "models.json",
        tmp_path,
        swapper=BrokenSwapper(),
    )
    with pytest.raises(WorkflowExecutionError, match="native_output_"):
        asyncio.run(backend.run(task, lambda _: asyncio.sleep(0)))
    assert store.result_variants(task.task_id, task.output_format) == []


def test_alphaface_compositing_preserves_canvas_and_outside_pixels() -> None:
    target = np.full((640, 900, 3), 65, dtype=np.uint8)
    crop = np.full((256, 256, 3), 190, dtype=np.uint8)
    matrix = np.array([[1.0, 0.0, -300.0], [0.0, 1.0, -120.0]])
    result = paste_aligned_face(target, crop, matrix)
    assert result.shape == target.shape
    assert result.dtype == np.uint8
    assert np.array_equal(result[:, :300], target[:, :300])
    assert np.array_equal(result[:, 556:], target[:, 556:])
    assert np.array_equal(result[:120], target[:120])
    assert np.array_equal(result[376:], target[376:])
    assert result[260, 428, 0] > target[260, 428, 0]


def test_alphaface_compositing_rejects_off_canvas() -> None:
    with pytest.raises(ValueError, match="intersect"):
        paste_aligned_face(
            np.zeros((32, 32, 3), dtype=np.uint8),
            np.zeros((256, 256, 3), dtype=np.uint8),
            np.array([[1.0, 0.0, 999.0], [0.0, 1.0, 999.0]]),
        )
