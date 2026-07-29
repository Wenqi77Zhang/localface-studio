"""Tests for deterministic, license-unapproved Open Images candidate queues."""

import csv
from pathlib import Path

import pytest

from localface_studio.benchmarking.open_images_candidates import (
    OpenImagesCandidateError,
    prepare_candidate_queue,
    write_candidate_queue,
)

BOX_FIELDS = (
    "ImageID",
    "LabelName",
    "XMin",
    "XMax",
    "YMin",
    "YMax",
    "IsOccluded",
    "IsTruncated",
    "IsGroupOf",
    "IsDepiction",
)
IMAGE_FIELDS = (
    "ImageID",
    "Subset",
    "OriginalURL",
    "OriginalLandingURL",
    "License",
    "AuthorProfileURL",
    "Author",
    "Title",
    "OriginalSize",
    "OriginalMD5",
    "Thumbnail300KURL",
    "Rotation",
)


def test_queue_filters_unsafe_rows_and_keeps_review_pending(tmp_path: Path) -> None:
    classes, boxes, images = _fixtures(tmp_path)
    _write_csv(
        boxes,
        BOX_FIELDS,
        [
            _box("safe-single", occluded="1"),
            _box("depiction", depiction="1"),
            _box("unknown-rotation"),
        ],
    )
    _write_csv(
        images,
        IMAGE_FIELDS,
        [
            _image("safe-single", rotation="90"),
            _image("depiction"),
            _image("unknown-rotation", rotation=""),
        ],
    )

    queue = prepare_candidate_queue(
        class_descriptions_path=classes,
        boxes_path=boxes,
        images_path=images,
        limit=1,
    )

    assert queue["review_status"] == "unreviewed"
    candidate = queue["candidates"][0]
    assert candidate["image_id"] == "safe-single"
    assert candidate["categories"] == ("single-face", "rotated", "occluded", "medium-face")
    assert candidate["review"]["status"] == "pending"
    assert candidate["seed_face_boxes"][0]["occluded"] is True


def test_queue_selection_is_deterministic(tmp_path: Path) -> None:
    classes, boxes, images = _fixtures(tmp_path)
    image_ids = ["one", "two", "three"]
    _write_csv(boxes, BOX_FIELDS, [_box(image_id) for image_id in image_ids])
    _write_csv(images, IMAGE_FIELDS, [_image(image_id) for image_id in image_ids])

    first = prepare_candidate_queue(
        class_descriptions_path=classes,
        boxes_path=boxes,
        images_path=images,
        limit=2,
    )
    second = prepare_candidate_queue(
        class_descriptions_path=classes,
        boxes_path=boxes,
        images_path=images,
        limit=2,
    )

    assert first == second
    assert len(first["candidates"]) == 2


def test_queue_round_robins_across_difficult_categories(tmp_path: Path) -> None:
    classes, boxes, images = _fixtures(tmp_path)
    rows = [
        _box("rotated"),
        _box("truncated", truncated="1"),
        _box("occluded", occluded="1"),
        _box("multi"),
        _box("multi", x_min="0.55", x_max="0.85"),
    ]
    _write_csv(boxes, BOX_FIELDS, rows)
    _write_csv(
        images,
        IMAGE_FIELDS,
        [
            _image("rotated", rotation="90"),
            _image("truncated"),
            _image("occluded"),
            _image("multi"),
        ],
    )

    queue = prepare_candidate_queue(
        class_descriptions_path=classes,
        boxes_path=boxes,
        images_path=images,
        limit=4,
    )

    categories = {
        category for candidate in queue["candidates"] for category in candidate["categories"]
    }
    assert {"rotated", "truncated", "occluded", "multi-face"}.issubset(categories)


def test_queue_writer_refuses_to_replace_human_review(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    write_candidate_queue(path, {"schema_version": 1})

    with pytest.raises(OpenImagesCandidateError, match="already exists"):
        write_candidate_queue(path, {"schema_version": 2})

    assert '"schema_version": 1' in path.read_text(encoding="utf-8")


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    classes = tmp_path / "classes.csv"
    classes.write_text("/m/0dzct,Human face\n/m/example,Example\n", encoding="utf-8")
    return classes, tmp_path / "boxes.csv", tmp_path / "images.csv"


def _box(
    image_id: str,
    *,
    occluded: str = "0",
    truncated: str = "0",
    depiction: str = "0",
    x_min: str = "0.1",
    x_max: str = "0.4",
) -> dict[str, str]:
    return {
        "ImageID": image_id,
        "LabelName": "/m/0dzct",
        "XMin": x_min,
        "XMax": x_max,
        "YMin": "0.2",
        "YMax": "0.5",
        "IsOccluded": occluded,
        "IsTruncated": truncated,
        "IsGroupOf": "0",
        "IsDepiction": depiction,
    }


def _image(image_id: str, *, rotation: str = "0") -> dict[str, str]:
    return {
        "ImageID": image_id,
        "Subset": "validation",
        "OriginalURL": f"https://images.example/{image_id}.jpg",
        "OriginalLandingURL": f"https://landing.example/{image_id}",
        "License": "https://creativecommons.org/licenses/by/2.0/",
        "AuthorProfileURL": "https://landing.example/author",
        "Author": "Example Author",
        "Title": "Example title",
        "OriginalSize": "12345",
        "OriginalMD5": "example-md5",
        "Thumbnail300KURL": "",
        "Rotation": rotation,
    }


def _write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
