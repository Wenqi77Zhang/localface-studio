"""Strict model manifest parsing and local artifact integrity verification."""

import json
from dataclasses import dataclass
from hashlib import file_digest
from pathlib import Path
from typing import Any


class ModelManifestError(RuntimeError):
    """Fail closed with a stable code and without exposing an absolute local path."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """Verified manifest facts needed by a model adapter."""

    model_id: str
    role: str
    version: str
    filename: str
    relative_path: Path
    sha256: str
    size_bytes: int
    commercial_mode_allowed: bool


def load_model_artifact(manifest_path: Path, model_id: str) -> ModelArtifact:
    """Load one model entry from a versioned JSON manifest."""
    if not model_id.strip():
        raise ValueError("model_id must not be blank")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelManifestError("model_manifest_missing") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelManifestError("model_manifest_invalid") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ModelManifestError("model_manifest_invalid")
    models = raw.get("models")
    if not isinstance(models, list):
        raise ModelManifestError("model_manifest_invalid")
    matching = [
        entry for entry in models if isinstance(entry, dict) and entry.get("id") == model_id
    ]
    if len(matching) != 1:
        raise ModelManifestError("model_manifest_entry_missing")
    return _parse_artifact(matching[0])


def verify_model_artifact(artifact: ModelArtifact, project_root: Path) -> Path:
    """Resolve and verify a model while keeping the absolute path out of errors."""
    root = project_root.resolve()
    model_path = (root / artifact.relative_path).resolve()
    if not model_path.is_relative_to(root):
        raise ModelManifestError("model_path_outside_project")
    try:
        stat = model_path.stat()
    except OSError as error:
        raise ModelManifestError("model_file_missing") from error
    if not model_path.is_file():
        raise ModelManifestError("model_file_missing")
    if stat.st_size != artifact.size_bytes:
        raise ModelManifestError("model_size_mismatch")
    try:
        with model_path.open("rb") as stream:
            digest = file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise ModelManifestError("model_file_unreadable") from error
    if digest != artifact.sha256:
        raise ModelManifestError("model_hash_mismatch")
    return model_path


def _parse_artifact(entry: dict[str, Any]) -> ModelArtifact:
    try:
        model_id = _required_string(entry, "id")
        role = _required_string(entry, "role")
        version = _required_string(entry, "version")
        filename = _required_string(entry, "filename")
        relative_path_value = _required_string(entry, "relative_path")
        sha256 = _required_string(entry, "sha256").lower()
        size_bytes = entry["size_bytes"]
        commercial_mode_allowed = entry["commercial_mode_allowed"]
    except (KeyError, TypeError, ValueError) as error:
        raise ModelManifestError("model_manifest_entry_invalid") from error
    relative_path = Path(relative_path_value)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ModelManifestError("model_manifest_entry_invalid")
    if relative_path.name != filename:
        raise ModelManifestError("model_manifest_entry_invalid")
    if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
        raise ModelManifestError("model_manifest_entry_invalid")
    if type(size_bytes) is not int or size_bytes < 1:
        raise ModelManifestError("model_manifest_entry_invalid")
    if type(commercial_mode_allowed) is not bool:
        raise ModelManifestError("model_manifest_entry_invalid")
    return ModelArtifact(
        model_id=model_id,
        role=role,
        version=version,
        filename=filename,
        relative_path=relative_path,
        sha256=sha256,
        size_bytes=size_bytes,
        commercial_mode_allowed=commercial_mode_allowed,
    )


def _required_string(entry: dict[str, Any], key: str) -> str:
    value = entry[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-blank string")
    return value
