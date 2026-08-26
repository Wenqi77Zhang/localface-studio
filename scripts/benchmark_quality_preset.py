"""Measure the model-free balanced preset against one baseline result."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from localface_studio.backends.face_quality import face_blend_mask, harmonize_face_color
from localface_studio.backends.scrfd import ScrfdResearchFaceDetector
from localface_studio.infrastructure.image_decoding import decode_bgr_autorotated

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    args = parse_args()
    if not args.accept_research_license:
        raise SystemExit("Pass --accept-research-license to load the SCRFD research model.")
    target = decode_bgr_autorotated(Path(args.target))
    baseline = decode_bgr_autorotated(Path(args.baseline))
    if target.shape != baseline.shape:
        raise SystemExit("Target and baseline output dimensions must match.")
    detector = ScrfdResearchFaceDetector.from_manifest(
        ROOT / "config" / "models.json",
        ROOT,
        research_license_accepted=True,
    )
    faces = detector.detect(target)
    if len(faces) < args.target_face:
        raise SystemExit("Requested target face was not detected.")
    face = faces[args.target_face - 1]
    balanced = harmonize_face_color(target, baseline, face)
    mask = face_blend_mask(target.shape[1], target.shape[0], face)
    core = mask >= 0.8
    outside = mask < 0.001
    target_lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype(np.float32)
    baseline_lab = cv2.cvtColor(baseline, cv2.COLOR_BGR2LAB).astype(np.float32)
    balanced_lab = cv2.cvtColor(balanced, cv2.COLOR_BGR2LAB).astype(np.float32)
    report = {
        "schema_version": 1,
        "target_face": args.target_face,
        "core_target_lab_mae": {
            "identity": _mae(baseline_lab[core], target_lab[core]),
            "balanced": _mae(balanced_lab[core], target_lab[core]),
        },
        "balanced_vs_identity_core_bgr_mae": _mae(balanced[core], baseline[core]),
        "balanced_vs_identity_max_absolute_change": int(
            np.max(np.abs(balanced.astype(np.int16) - baseline.astype(np.int16)))
        ),
        "outside_mask_pixels_changed": int(
            np.count_nonzero(np.any(balanced[outside] != baseline[outside], axis=1))
        ),
        "limitations": [
            "Colour-distance metrics do not measure identity preservation.",
            "This single-case report is an implementation ablation, not a population claim.",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), balanced):
        raise RuntimeError("Failed to write balanced comparison image.")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, separators=(",", ":")))


def _mae(left: np.ndarray, right: np.ndarray) -> float:
    return round(float(np.mean(np.abs(left.astype(np.float32) - right.astype(np.float32)))), 6)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--target-face", type=int, default=1)
    parser.add_argument("--accept-research-license", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
