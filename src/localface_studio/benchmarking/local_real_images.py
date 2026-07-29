"""Create a Git-ignored workspace for reviewed real-image benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCAL_WORKSPACE_SCHEMA_VERSION = 1
OPEN_IMAGES_FACTS_URL = "https://storage.googleapis.com/openimages/web/factsfigures_v7.html"
OPEN_IMAGES_DOWNLOAD_URL = "https://storage.googleapis.com/openimages/web/download_v7.html"


class LocalBenchmarkWorkspaceError(ValueError):
    """Raised when a local benchmark workspace would be unsafe."""


def initialize_local_workspace(workspace: Path, *, allowed_root: Path) -> tuple[Path, ...]:
    """Create private templates without overwriting an existing review ledger."""
    resolved_workspace = workspace.resolve()
    resolved_allowed_root = allowed_root.resolve()
    if not resolved_workspace.is_relative_to(resolved_allowed_root):
        raise LocalBenchmarkWorkspaceError("local benchmark must stay under the private root")

    images = resolved_workspace / "images"
    reports = resolved_workspace / "reports"
    images.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    ledger_path = resolved_workspace / "license-ledger.json"
    manifest_path = resolved_workspace / "manifest.draft.json"
    instructions_path = resolved_workspace / "LOCAL_ONLY.txt"
    created: list[Path] = []
    created.extend(_write_new_json(ledger_path, _empty_license_ledger()))
    created.extend(_write_new_json(manifest_path, _empty_detection_manifest()))
    created.extend(
        _write_new_text(
            instructions_path,
            (
                "LOCAL ONLY - DO NOT COMMIT OR UPLOAD\n"
                "Real images, annotations, reports, and the license ledger stay on this device.\n"
                "Use repository-relative asset names only; never record an absolute local path.\n"
            ),
        )
    )
    return tuple(created)


def _empty_license_ledger() -> dict[str, Any]:
    return {
        "schema_version": LOCAL_WORKSPACE_SCHEMA_VERSION,
        "dataset": {
            "name": "Open Images V7",
            "facts_url": OPEN_IMAGES_FACTS_URL,
            "download_url": OPEN_IMAGES_DOWNLOAD_URL,
        },
        "privacy_rules": {
            "identity_recognition": False,
            "demographic_inference": False,
            "face_crops_persisted": False,
            "absolute_local_paths_allowed": False,
        },
        "target_accepted_cases": 20,
        "candidates": [],
    }


def _empty_detection_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "detector_id": "yunet-opencv",
        "cases": [],
        "_draft_notice": (
            "Remove this field after at least one reviewed case is added; "
            "the strict benchmark runner intentionally rejects draft manifests."
        ),
    }


def _write_new_json(path: Path, payload: dict[str, Any]) -> list[Path]:
    return _write_new_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )


def _write_new_text(path: Path, content: str) -> list[Path]:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except FileExistsError:
        return []
    return [path]
