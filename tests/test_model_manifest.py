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

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_public_catalog_registers_research_scrfd_without_commercial_permission() -> None:
    artifact = load_model_artifact(
        PROJECT_ROOT / "config/models.json",
        "scrfd-insightface-research",
    )

    assert artifact.role == "face_detector"
    assert artifact.version == "buffalo_m-v0.7-20260312"
    assert artifact.filename == "det_2.5g.onnx"
    assert artifact.relative_path == Path("models/detectors/scrfd/det_2.5g.onnx")
    assert artifact.sha256 == "041f73f47371333d1d17a6fee6c8ab4e6aecabefe398ff32cca4e2d5eaee0af9"
    assert artifact.size_bytes == 3292009
    assert artifact.commercial_mode_allowed is False


@pytest.mark.parametrize(
    ("model_id", "role", "filename", "size_bytes", "sha256_value"),
    [
        (
            "inswapper-128-research",
            "face_swapper",
            "inswapper_128.onnx",
            554253681,
            "e4a3f08c753cb72d04e10aa0f7dbe3deebbf39567d4ead6dce08e98aa49e16af",
        ),
        (
            "arcface-w600k-r50-research",
            "face_encoder",
            "w600k_r50.onnx",
            174383860,
            "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
        ),
    ],
)
def test_public_catalog_registers_research_swap_pipeline_without_commercial_permission(
    model_id: str,
    role: str,
    filename: str,
    size_bytes: int,
    sha256_value: str,
) -> None:
    artifact = load_model_artifact(PROJECT_ROOT / "config/models.json", model_id)

    assert artifact.role == role
    assert artifact.filename == filename
    assert artifact.size_bytes == size_bytes
    assert artifact.sha256 == sha256_value
    assert artifact.commercial_mode_allowed is False


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
