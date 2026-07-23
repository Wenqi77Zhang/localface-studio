"""Storage boundary for task metadata."""

from datetime import datetime
from typing import Protocol

from localface_studio.domain.tasks import TaskRecord


class DuplicateTaskError(RuntimeError):
    """Raised when a generated task identifier already exists."""


class ConcurrentTaskUpdateError(RuntimeError):
    """Raised when another operation updated a task before the current save."""


class TaskRepository(Protocol):
    """Persistence operations needed by task services without exposing SQLite."""

    def create(self, task: TaskRecord) -> None:
        """Persist a new task."""
        ...

    def get_for_actor(self, task_id: str, actor_id: str) -> TaskRecord | None:
        """Return a task only when it belongs to the requesting actor."""
        ...

    def save(self, task: TaskRecord, *, expected_version: int) -> None:
        """Atomically save a task revision when the stored version still matches."""
        ...

    def count_unfinished_for_actor(self, actor_id: str) -> int:
        """Count queued and running tasks for a local session or future account."""
        ...

    def list_due_for_expiry(self, at: datetime) -> list[TaskRecord]:
        """Return successful results whose retention deadline has passed."""
        ...

    def list_available_results_for_actor(
        self,
        actor_id: str,
        at: datetime,
    ) -> list[TaskRecord]:
        """Return one actor's unexpired successful results, newest first."""
        ...

    def list_all(self) -> list[TaskRecord]:
        """Return minimal task records for process-restart recovery."""
        ...
