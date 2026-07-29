"""Prepare a local-only review queue from official Open Images metadata."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

FACE_CLASS_NAME = "Human face"
DECLARED_LICENSE = "https://creativecommons.org/licenses/by/2.0/"
QUEUE_SCHEMA_VERSION = 1
REQUIRED_METADATA_FIELDS = (
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
    "Rotation",
)
BUCKET_ORDER = (
    "rotated",
    "truncated",
    "occluded",
    "small-face",
    "multi-face",
    "single-face",
    "large-face",
    "medium-face",
)


class OpenImagesCandidateError(ValueError):
    """Raised when official metadata is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class SeedFaceBox:
    """Open Images box used only as a seed for later human review."""

    x: float
    y: float
    width: float
    height: float
    occluded: bool
    truncated: bool


@dataclass(frozen=True, slots=True)
class Candidate:
    """One unapproved image candidate with provenance and review hints."""

    image_id: str
    subset: str
    original_url: str
    original_landing_url: str
    declared_license: str
    author_profile_url: str
    author: str
    title: str
    original_size: int
    original_md5: str
    rotation: int
    categories: tuple[str, ...]
    seed_face_boxes: tuple[SeedFaceBox, ...]


def prepare_candidate_queue(
    *,
    class_descriptions_path: Path,
    boxes_path: Path,
    images_path: Path,
    limit: int = 40,
) -> dict[str, Any]:
    """Join official CSV files and return a deterministic, diverse review queue."""
    if limit < 1:
        raise OpenImagesCandidateError("candidate limit must be positive")
    face_mid = _face_mid(class_descriptions_path)
    grouped_boxes = _load_eligible_face_boxes(boxes_path, face_mid=face_mid)
    candidates = _load_candidates(images_path, grouped_boxes=grouped_boxes)
    selected = _select_diverse(candidates, limit=limit)
    if len(selected) < limit:
        raise OpenImagesCandidateError(
            f"only {len(selected)} eligible candidates were available for limit {limit}"
        )
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "review_status": "unreviewed",
        "source_files": {
            "class_descriptions": class_descriptions_path.name,
            "boxes": boxes_path.name,
            "images": images_path.name,
        },
        "selection": {
            "face_mid": face_mid,
            "declared_license": DECLARED_LICENSE,
            "candidate_count": len(selected),
            "notice": (
                "Dataset metadata is not license approval. Open each original landing page "
                "and complete a human privacy and license review before downloading pixels."
            ),
        },
        "candidates": [
            {
                "case_id": f"real-candidate-{index:03d}",
                **asdict(candidate),
                "review": {
                    "status": "pending",
                    "landing_page_checked_at": None,
                    "license_checked_at": None,
                    "decision_reason": None,
                },
            }
            for index, candidate in enumerate(selected, start=1)
        ],
    }


def write_candidate_queue(path: Path, payload: dict[str, Any]) -> None:
    """Write local review data, refusing to replace an existing queue."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except FileExistsError as error:
        raise OpenImagesCandidateError("candidate queue already exists") from error


def _face_mid(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            matches = [mid.strip() for mid, name in csv.reader(stream) if name == FACE_CLASS_NAME]
    except (OSError, UnicodeError, csv.Error) as error:
        raise OpenImagesCandidateError("class descriptions are unreadable") from error
    if len(matches) != 1:
        raise OpenImagesCandidateError("Human face class mapping is missing or ambiguous")
    return matches[0]


def _load_eligible_face_boxes(
    path: Path,
    *,
    face_mid: str,
) -> dict[str, tuple[SeedFaceBox, ...]]:
    grouped: dict[str, list[SeedFaceBox]] = defaultdict(list)
    excluded_images: set[str] = set()
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {
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
            }
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise OpenImagesCandidateError("box annotation fields are incomplete")
            for row in reader:
                if row["LabelName"] != face_mid:
                    continue
                image_id = row["ImageID"]
                if _flag(row["IsGroupOf"]) or _flag(row["IsDepiction"]):
                    excluded_images.add(image_id)
                    continue
                x_min = float(row["XMin"])
                x_max = float(row["XMax"])
                y_min = float(row["YMin"])
                y_max = float(row["YMax"])
                grouped[image_id].append(
                    SeedFaceBox(
                        x=x_min,
                        y=y_min,
                        width=x_max - x_min,
                        height=y_max - y_min,
                        occluded=_flag(row["IsOccluded"]),
                        truncated=_flag(row["IsTruncated"]),
                    )
                )
    except OpenImagesCandidateError:
        raise
    except (OSError, UnicodeError, csv.Error, KeyError, ValueError) as error:
        raise OpenImagesCandidateError("box annotations are unreadable") from error
    return {
        image_id: tuple(boxes)
        for image_id, boxes in grouped.items()
        if image_id not in excluded_images and boxes
    }


def _load_candidates(
    path: Path,
    *,
    grouped_boxes: dict[str, tuple[SeedFaceBox, ...]],
) -> tuple[Candidate, ...]:
    candidates: list[Candidate] = []
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not set(REQUIRED_METADATA_FIELDS).issubset(
                reader.fieldnames
            ):
                raise OpenImagesCandidateError("image metadata fields are incomplete")
            for row in reader:
                boxes = grouped_boxes.get(row["ImageID"])
                fields_complete = all(row[field].strip() for field in REQUIRED_METADATA_FIELDS)
                if boxes is None or not fields_complete:
                    continue
                if row["License"] != DECLARED_LICENSE:
                    continue
                rotation = _rotation(row["Rotation"])
                if rotation is None:
                    continue
                candidates.append(
                    Candidate(
                        image_id=row["ImageID"],
                        subset=row["Subset"],
                        original_url=row["OriginalURL"],
                        original_landing_url=row["OriginalLandingURL"],
                        declared_license=row["License"],
                        author_profile_url=row["AuthorProfileURL"],
                        author=row["Author"],
                        title=row["Title"],
                        original_size=int(row["OriginalSize"]),
                        original_md5=row["OriginalMD5"],
                        rotation=rotation,
                        categories=_categories(boxes, rotation=rotation),
                        seed_face_boxes=boxes,
                    )
                )
    except OpenImagesCandidateError:
        raise
    except (OSError, UnicodeError, csv.Error, KeyError, ValueError) as error:
        raise OpenImagesCandidateError("image metadata is unreadable") from error
    return tuple(candidates)


def _select_diverse(candidates: tuple[Candidate, ...], *, limit: int) -> tuple[Candidate, ...]:
    ordered = sorted(
        candidates,
        key=lambda candidate: hashlib.sha256(candidate.image_id.encode()).digest(),
    )
    selected: list[Candidate] = []
    selected_ids: set[str] = set()
    while len(selected) < limit:
        progress = False
        for bucket in BUCKET_ORDER:
            candidate = next(
                (
                    item
                    for item in ordered
                    if item.image_id not in selected_ids and bucket in item.categories
                ),
                None,
            )
            if candidate is None:
                continue
            selected.append(candidate)
            selected_ids.add(candidate.image_id)
            progress = True
            if len(selected) >= limit:
                break
        if not progress:
            break
    if len(selected) < limit:
        for candidate in ordered:
            if candidate.image_id in selected_ids:
                continue
            selected.append(candidate)
            if len(selected) >= limit:
                break
    return tuple(selected)


def _categories(boxes: tuple[SeedFaceBox, ...], *, rotation: int) -> tuple[str, ...]:
    categories = ["single-face" if len(boxes) == 1 else "multi-face"]
    if rotation:
        categories.append("rotated")
    if any(box.occluded for box in boxes):
        categories.append("occluded")
    if any(box.truncated for box in boxes):
        categories.append("truncated")
    smallest_area = min(box.width * box.height for box in boxes)
    largest_area = max(box.width * box.height for box in boxes)
    if smallest_area < 0.02:
        categories.append("small-face")
    if largest_area > 0.15:
        categories.append("large-face")
    if smallest_area >= 0.02 and largest_area <= 0.15:
        categories.append("medium-face")
    return tuple(categories)


def _rotation(value: str) -> int | None:
    try:
        rotation = int(float(value))
    except ValueError:
        return None
    return rotation if rotation in {0, 90, 180, 270} else None


def _flag(value: str) -> bool:
    if value not in {"0", "1"}:
        raise OpenImagesCandidateError("annotation flag must be zero or one")
    return value == "1"
