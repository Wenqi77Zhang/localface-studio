"""Create a private Open Images candidate queue without downloading pixels."""

from pathlib import Path

from localface_studio.benchmarking.open_images_candidates import (
    prepare_candidate_queue,
    write_candidate_queue,
)

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "runtime" / "benchmarks" / "real"
METADATA = WORKSPACE / "metadata"
OUTPUT = WORKSPACE / "candidate-review-queue.json"


def main() -> None:
    payload = prepare_candidate_queue(
        class_descriptions_path=METADATA / "class-descriptions-boxable.csv",
        boxes_path=METADATA / "validation-annotations-bbox.csv",
        images_path=METADATA / "validation-images-with-rotation.csv",
    )
    write_candidate_queue(OUTPUT, payload)
    print(f"Prepared {len(payload['candidates'])} unreviewed local candidates.")
    print("No image pixels were downloaded and no candidate was approved.")
    print(f"Private queue: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
