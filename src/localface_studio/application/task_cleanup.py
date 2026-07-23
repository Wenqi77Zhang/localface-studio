"""Fail-closed recovery and retention cleanup for task workspaces."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from localface_studio.application.task_creation import utc_now
from localface_studio.application.task_repository import TaskRepository
from localface_studio.domain.tasks import TaskRecord, TaskStatus, transition_task

DEFAULT_CLEANUP_INTERVAL_SECONDS = 60.0


class CleanupWorkspaceStore(Protocol):
    """Minimal filesystem boundary required by retention cleanup."""

    def remove(self, task_id: str) -> None:
        """Remove one canonical task workspace."""
        ...

    def list_task_ids(self) -> tuple[str, ...]:
        """List canonical task workspace identifiers."""
        ...


class TaskCleanupService:
    """Reconcile restart remnants and enforce result retention deadlines."""

    def __init__(
        self,
        repository: TaskRepository,
        workspaces: CleanupWorkspaceStore,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._workspaces = workspaces
        self._clock = clock

    def recover_startup(self) -> None:
        """Remove orphaned bytes and terminalize work abandoned by a restart."""
        now = self._clock()
        records = self._repository.list_all()
        known_ids = {task.task_id for task in records}
        for task in records:
            if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                task = self._transition(task, TaskStatus.TIMED_OUT, now)
            elif task.status is TaskStatus.SUCCEEDED and task.expires_at <= now:
                task = self._transition(task, TaskStatus.EXPIRED, now)
            if task.status is not TaskStatus.SUCCEEDED:
                self._workspaces.remove(task.task_id)

        for task_id in self._workspaces.list_task_ids():
            if task_id not in known_ids:
                self._workspaces.remove(task_id)

    def expire_due(self) -> None:
        """Expire successful results whose explicit retention deadline elapsed."""
        now = self._clock()
        for task in self._repository.list_due_for_expiry(now):
            self._transition(task, TaskStatus.EXPIRED, now)
            self._workspaces.remove(task.task_id)

    async def run_periodically(
        self,
        stop: asyncio.Event,
        *,
        interval_seconds: float = DEFAULT_CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        """Wait between cleanup passes and stop promptly during app shutdown."""
        if interval_seconds <= 0:
            raise ValueError("cleanup interval must be positive")
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                self.expire_due()

    def _transition(
        self,
        task: TaskRecord,
        target: TaskStatus,
        at: datetime,
    ) -> TaskRecord:
        updated = transition_task(
            task,
            target,
            at=max(at, task.updated_at),
            current_node=task.current_node,
        )
        self._repository.save(updated, expected_version=task.version)
        return updated
