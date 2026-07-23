"""Random, fixed-name task workspace management."""

import re
import shutil
from pathlib import Path

from localface_studio.domain.images import ImageRole
from localface_studio.domain.tasks import OutputFormat

_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
_INPUT_SUFFIXES = ("png", "jpg", "webp")


class TaskWorkspaceStore:
    """Keep user-controlled names out of filesystem paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def create(self, task_id: str) -> Path:
        workspace = self._workspace(task_id)
        workspace.mkdir(mode=0o700)
        return workspace

    def staging_path(self, task_id: str, role: ImageRole) -> Path:
        return self._workspace(task_id) / f"{role.value}.part"

    def finalize(
        self,
        task_id: str,
        role: ImageRole,
        staging_path: Path,
        extension: str,
    ) -> str:
        workspace = self._workspace(task_id)
        if staging_path.parent.resolve() != workspace or staging_path.name != f"{role.value}.part":
            raise ValueError("staging path is outside the task workspace")
        stored_name = f"{role.value}.{self._canonical_suffix(extension)}"
        staging_path.replace(workspace / stored_name)
        return stored_name

    def remove(self, task_id: str) -> None:
        workspace = self._workspace(task_id)
        if workspace.exists():
            shutil.rmtree(workspace)

    def input_path(self, task_id: str, role: ImageRole) -> Path:
        """Resolve one canonical input without accepting a caller-controlled path."""
        workspace = self._workspace(task_id)
        matches = [
            candidate
            for suffix in _INPUT_SUFFIXES
            if (candidate := workspace / f"{role.value}.{suffix}").is_file()
        ]
        if len(matches) != 1:
            raise FileNotFoundError(f"expected one canonical {role.value} image")
        return matches[0]

    def result_path(self, task_id: str, output_format: OutputFormat) -> Path:
        """Return the fixed final result path for the requested encoding."""
        suffix = "jpg" if output_format is OutputFormat.JPEG else "png"
        return self._workspace(task_id) / f"result.{suffix}"

    def result_staging_path(self, task_id: str) -> Path:
        """Return a fixed temporary result path used for atomic publication."""
        return self._workspace(task_id) / "result.part"

    def _workspace(self, task_id: str) -> Path:
        if _TASK_ID.fullmatch(task_id) is None:
            raise ValueError("invalid task identifier")
        workspace = (self._root / task_id).resolve()
        if workspace.parent != self._root:
            raise ValueError("task workspace escaped its storage root")
        return workspace

    @staticmethod
    def _canonical_suffix(extension: str) -> str:
        if extension == "jpeg":
            return "jpg"
        if extension in {"png", "webp"}:
            return extension
        raise ValueError("unsupported canonical image extension")
