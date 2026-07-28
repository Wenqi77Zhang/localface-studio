"""Benchmark manifest and matching tests without personal image fixtures."""

import json
from pathlib import Path, PurePosixPath

import pytest

from localface_studio.benchmarking.face_detection import (
    BenchmarkCase,
    BenchmarkManifestError,
    NormalizedBox,
    evaluate_case,
    load_benchmark_manifest,
)
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    stable_detection_id,
)

DETECTOR_ID = "yunet-opencv"


def test_manifest_loads_strict_safe_relative_cases(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "detector_id": DETECTOR_ID,
                "cases": [
                    {
                        "id": "synthetic-single-frontal",
                        "image": "assets/single-frontal.png",
                        "categories": ["synthetic", "single", "frontal"],
                        "faces": [{"x": 0.25, "y": 0.2, "width": 0.5, "height": 0.6}],
                        "provenance": "Generated specifically for this benchmark.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_benchmark_manifest(manifest_path)

    assert manifest.detector_id == DETECTOR_ID
    assert manifest.cases[0].image_path.as_posix() == "assets/single-frontal.png"
    assert manifest.cases[0].faces[0].width == 0.5


@pytest.mark.parametrize(
    "image_path",
    ["../private.png", "/absolute/private.png", r"assets\private.png"],
)
def test_manifest_rejects_escaping_or_platform_specific_paths(
    tmp_path: Path,
    image_path: str,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "detector_id": DETECTOR_ID,
                "cases": [
                    {
                        "id": "unsafe",
                        "image": image_path,
                        "categories": ["synthetic"],
                        "faces": [],
                        "provenance": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkManifestError, match="safe and relative"):
        load_benchmark_manifest(manifest_path)


def test_evaluation_uses_one_to_one_iou_matching() -> None:
    case = BenchmarkCase(
        case_id="two-faces",
        image_path=PurePosixPath("two.png"),
        categories=("synthetic", "multi"),
        faces=(
            NormalizedBox(x=0.1, y=0.1, width=0.2, height=0.3),
            NormalizedBox(x=0.6, y=0.1, width=0.2, height=0.3),
        ),
        provenance="generated",
    )
    evaluation = evaluate_case(
        case,
        (
            _face(FaceBox(x=10, y=10, width=20, height=30)),
            _face(FaceBox(x=61, y=10, width=20, height=30)),
            _face(FaceBox(x=35, y=60, width=10, height=10)),
        ),
        image_width=100,
        image_height=100,
    )

    assert evaluation.true_positives == 2
    assert evaluation.false_positives == 1
    assert evaluation.false_negatives == 0
    assert evaluation.recall == 1
    assert evaluation.precision == pytest.approx(2 / 3)


def _face(box: FaceBox) -> DetectedFace:
    landmarks = tuple(FacePoint(x=box.x + index + 1, y=box.y + index + 1) for index in range(5))
    return DetectedFace(
        detection_id=stable_detection_id(DETECTOR_ID, box, landmarks),
        detector_id=DETECTOR_ID,
        box=box,
        landmarks=landmarks,
        confidence=0.95,
    )
