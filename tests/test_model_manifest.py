"""Model manifest validation and fail-closed artifact verification tests."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from localface_studio.infrastructure.model_manifest import (
    ModelManifestError,
    load_model_artifact,
    verify_model_artifact,
)


def write_manifest(
    root: Path,
    model_bytes: bytes,
    *,
    relative_path: str = "models/model.onnx",
) -> Path:
    model_path = root / relative_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(model_bytes)
    manifest = {
        "schema_version": 1,
        "models": [
            {
                "id": "yunet-opencv",
                "role": "face_detector",
                "version": "test",
                "filename": "model.onnx",
                "relative_path": relative_path,
                "sha256": sha256(model_bytes).hexdigest(),
                "size_bytes": len(model_bytes),
                "commercial_mode_allowed": True,
            }
        ],
    }
    manifest_path = root / "models.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_manifest_resolves_verified_model_inside_project(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, b"verified-model")

    artifact = load_model_artifact(manifest_path, "yunet-opencv")

    assert artifact.role == "face_detector"
    assert verify_model_artifact(artifact, tmp_path) == tmp_path / "models/model.onnx"


def test_model_hash_mismatch_fails_without_exposing_local_path(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, b"expected")
    artifact = load_model_artifact(manifest_path, "yunet-opencv")
    (tmp_path / artifact.relative_path).write_bytes(b"tampered")

    with pytest.raises(ModelManifestError) as captured:
        verify_model_artifact(artifact, tmp_path)

    assert captured.value.code == "model_hash_mismatch"
    assert str(tmp_path) not in str(captured.value)


def test_model_missing_and_size_mismatch_have_distinct_codes(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, b"expected")
    artifact = load_model_artifact(manifest_path, "yunet-opencv")
    model_path = tmp_path / artifact.relative_path
    model_path.write_bytes(b"wrong-size")

    with pytest.raises(ModelManifestError, match="model_size_mismatch"):
        verify_model_artifact(artifact, tmp_path)
    model_path.unlink()
    with pytest.raises(ModelManifestError, match="model_file_missing"):
        verify_model_artifact(artifact, tmp_path)


def test_manifest_rejects_traversal_and_unknown_model(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, b"model")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["models"][0]["relative_path"] = "../model.onnx"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ModelManifestError, match="model_manifest_entry_invalid"):
        load_model_artifact(manifest_path, "yunet-opencv")
    with pytest.raises(ModelManifestError, match="model_manifest_entry_missing"):
        load_model_artifact(write_manifest(tmp_path, b"model"), "missing")


def test_manifest_rejects_missing_file_invalid_json_and_schema(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ModelManifestError, match="model_manifest_missing"):
        load_model_artifact(missing, "yunet-opencv")

    manifest_path = tmp_path / "models.json"
    manifest_path.write_text("{", encoding="utf-8")
    with pytest.raises(ModelManifestError, match="model_manifest_invalid"):
        load_model_artifact(manifest_path, "yunet-opencv")

    manifest_path.write_text(json.dumps({"schema_version": 2, "models": []}), encoding="utf-8")
    with pytest.raises(ModelManifestError, match="model_manifest_invalid"):
        load_model_artifact(manifest_path, "yunet-opencv")

    manifest_path.write_text(
        json.dumps({"schema_version": 1, "models": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ModelManifestError, match="model_manifest_invalid"):
        load_model_artifact(manifest_path, "yunet-opencv")
    with pytest.raises(ValueError, match="model_id"):
        load_model_artifact(manifest_path, " ")


def test_verification_rejects_paths_outside_project(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, b"model")
    artifact = load_model_artifact(manifest_path, "yunet-opencv")

    with pytest.raises(ModelManifestError, match="model_path_outside_project"):
        verify_model_artifact(replace(artifact, relative_path=Path("../escape.onnx")), tmp_path)
