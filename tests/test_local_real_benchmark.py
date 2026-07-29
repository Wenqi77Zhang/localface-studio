"""Safety tests for the private real-image benchmark workspace."""

import json
from pathlib import Path

import pytest

from localface_studio.benchmarking.local_real_images import (
    LocalBenchmarkWorkspaceError,
    initialize_local_workspace,
)


def test_initializer_creates_private_templates_without_identity_processing(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "runtime"
    workspace = private_root / "benchmarks" / "real"

    created = initialize_local_workspace(workspace, allowed_root=private_root)

    assert len(created) == 3
    assert (workspace / "images").is_dir()
    assert (workspace / "reports").is_dir()
    ledger = json.loads((workspace / "license-ledger.json").read_text(encoding="utf-8"))
    assert ledger["target_accepted_cases"] == 20
    assert ledger["candidates"] == []
    assert ledger["privacy_rules"] == {
        "identity_recognition": False,
        "demographic_inference": False,
        "face_crops_persisted": False,
        "absolute_local_paths_allowed": False,
    }
    draft = json.loads((workspace / "manifest.draft.json").read_text(encoding="utf-8"))
    assert draft["detector_id"] == "yunet-opencv"
    assert draft["cases"] == []


def test_initializer_is_idempotent_and_does_not_overwrite_review_work(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "runtime"
    workspace = private_root / "benchmarks" / "real"
    initialize_local_workspace(workspace, allowed_root=private_root)
    ledger_path = workspace / "license-ledger.json"
    ledger_path.write_text('{"reviewed": true}\n', encoding="utf-8")

    created = initialize_local_workspace(workspace, allowed_root=private_root)

    assert created == ()
    assert ledger_path.read_text(encoding="utf-8") == '{"reviewed": true}\n'


def test_initializer_rejects_workspace_outside_private_root(tmp_path: Path) -> None:
    with pytest.raises(LocalBenchmarkWorkspaceError, match="private root"):
        initialize_local_workspace(
            tmp_path / "public" / "benchmark",
            allowed_root=tmp_path / "runtime",
        )
