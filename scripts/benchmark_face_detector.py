"""Run the local YuNet adapter against a licensed benchmark manifest."""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import cv2
import numpy as np
from PIL import Image

from localface_studio.backends.yunet import YuNetFaceDetector
from localface_studio.benchmarking.face_detection import (
    BenchmarkManifestError,
    CaseEvaluation,
    evaluate_case,
    load_benchmark_manifest,
)
from localface_studio.domain.faces import DetectedFace

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "runtime" / "benchmarks" / "yunet-report.json"
MEASURED_RUNS = 5
WARMUP_RUNS = 2


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    manifest = load_benchmark_manifest(manifest_path)
    detector = YuNetFaceDetector.from_manifest(
        ROOT / "config" / "models.json",
        ROOT,
    )
    if detector.detector_id != manifest.detector_id:
        raise BenchmarkManifestError("benchmark_detector_mismatch")

    case_reports: list[dict[str, Any]] = []
    evaluations: list[CaseEvaluation] = []
    for case in manifest.cases:
        image_path = (manifest_path.parent / Path(case.image_path.as_posix())).resolve()
        if not image_path.is_relative_to(manifest_path.parent):
            raise BenchmarkManifestError("benchmark_image_escaped_manifest_directory")
        image = decode_bgr(image_path)
        for _ in range(WARMUP_RUNS):
            detector.detect(image)
        durations: list[float] = []
        detections: tuple[DetectedFace, ...] = ()
        for _ in range(MEASURED_RUNS):
            started = perf_counter()
            detections = detector.detect(image)
            durations.append((perf_counter() - started) * 1000)
        height, width = image.shape[:2]
        evaluation = evaluate_case(
            case,
            detections,
            image_width=width,
            image_height=height,
        )
        evaluations.append(evaluation)
        case_reports.append(
            {
                **asdict(evaluation),
                "categories": list(case.categories),
                "median_duration_ms": round(median(durations), 3),
                "maximum_duration_ms": round(max(durations), 3),
            }
        )

    output: Path = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "detector_id": detector.detector_id,
        "manifest": manifest_path.name,
        "environment": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "platform": platform.system(),
            "machine": platform.machine(),
        },
        "summary": summarize(evaluations),
        "cases": case_reports,
    }
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Report written to: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate YuNet without persisting image pixels or face crops."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to a reviewed benchmark manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Local JSON report path; defaults under ignored runtime/.",
    )
    return parser.parse_args()


def decode_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def summarize(evaluations: list[CaseEvaluation]) -> dict[str, float | int]:
    expected = sum(item.expected_faces for item in evaluations)
    detected = sum(item.detected_faces for item in evaluations)
    true_positives = sum(item.true_positives for item in evaluations)
    false_positives = sum(item.false_positives for item in evaluations)
    false_negatives = sum(item.false_negatives for item in evaluations)
    return {
        "case_count": len(evaluations),
        "expected_faces": expected,
        "detected_faces": detected,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "recall": round(true_positives / expected, 6) if expected else 1.0,
        "precision": round(true_positives / detected, 6) if detected else float(not expected),
    }


if __name__ == "__main__":
    main()
