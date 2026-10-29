"""Restart recovery, orphan removal, and periodic retention tests."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from localface_studio.application.task_cleanup import TaskCleanupService
from localface_studio.domain.tasks import (
    OutputFormat,
    TaskRecord,
    TaskStatus,
    transition_task,
)
from localface_studio.infrastructure.sqlite_tasks import SqliteTaskRepository
from localface_studio.infrastructure.task_workspaces import TaskWorkspaceStore


def task_id(label: str) -> str:
    return f"{label:-<32}"


def create_task(
    repository: SqliteTaskRepository,
    *,
    identifier: str,
    created_at: datetime,
    expires_at: datetime,
    status: TaskStatus,
) -> TaskRecord:
    task = TaskRecord(
        task_id=identifier,
        actor_id="private-actor",
        status=TaskStatus.QUEUED,
        created_at=created_at,
        updated_at=created_at,
        expires_at=expires_at,
        consent_version="2026-07-23-v1",
        consented_at=created_at,
        output_format=OutputFormat.PNG,
        watermark_enabled=True,
    )
    repository.create(task)
    if status is not TaskStatus.QUEUED:
        running = transition_task(task, TaskStatus.RUNNING, at=created_at + timedelta(seconds=1))
        repository.save(running, expected_version=task.version)
        task = running
    if status is TaskStatus.SUCCEEDED:
        succeeded = transition_task(
            task,
            TaskStatus.SUCCEEDED,
            at=created_at + timedelta(seconds=2),
        )
        repository.save(succeeded, expected_version=task.version)
        task = succeeded
    return task


def test_startup_recovery_preserves_only_unexpired_success(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    repository = SqliteTaskRepository(tmp_path / "tasks.sqlite3")
    repository.initialize()
    workspaces = TaskWorkspaceStore(tmp_path / "tasks")
    queued = create_task(
        repository,
        identifier=task_id("queued"),
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(minutes=25),
        status=TaskStatus.QUEUED,
    )
    due = create_task(
        repository,
        identifier=task_id("due"),
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        status=TaskStatus.SUCCEEDED,
    )
    retained = create_task(
        repository,
        identifier=task_id("retained"),
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(minutes=25),
        status=TaskStatus.SUCCEEDED,
    )
    orphan_id = task_id("orphan")
    for identifier in (queued.task_id, due.task_id, retained.task_id, orphan_id):
        workspaces.create(identifier)

    TaskCleanupService(repository, workspaces, clock=lambda: now).recover_startup()

    recovered_queued = repository.get_for_actor(queued.task_id, queued.actor_id)
    recovered_due = repository.get_for_actor(due.task_id, due.actor_id)
    assert recovered_queued is not None
    assert recovered_queued.status is TaskStatus.TIMED_OUT
    assert recovered_due is not None
    assert recovered_due.status is TaskStatus.EXPIRED
    assert workspaces.list_task_ids() == (retained.task_id,)


def test_periodic_cleanup_expires_due_result_and_stops_promptly(tmp_path: Path) -> None:
    async def scenario() -> None:
        now = datetime.now(UTC)
        repository = SqliteTaskRepository(tmp_path / "tasks.sqlite3")
        repository.initialize()
        workspaces = TaskWorkspaceStore(tmp_path / "tasks")
        due = create_task(
            repository,
            identifier=task_id("periodic"),
            created_at=now - timedelta(minutes=2),
            expires_at=now - timedelta(minutes=1),
            status=TaskStatus.SUCCEEDED,
        )
        workspaces.create(due.task_id)
        cleanup = TaskCleanupService(repository, workspaces, clock=lambda: now)
        stop = asyncio.Event()
        worker = asyncio.create_task(cleanup.run_periodically(stop, interval_seconds=0.01))
        await asyncio.sleep(0.03)
        stop.set()
        await worker

        expired = repository.get_for_actor(due.task_id, due.actor_id)
        assert expired is not None and expired.status is TaskStatus.EXPIRED
        assert workspaces.list_task_ids() == ()

    asyncio.run(scenario())


def test_expiry_retries_busy_files_instead_of_forgetting_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    repository = SqliteTaskRepository(tmp_path / "tasks.sqlite3")
    repository.initialize()
    workspaces = TaskWorkspaceStore(tmp_path / "tasks")
    due = create_task(
        repository,
        identifier=task_id("busy"),
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        status=TaskStatus.SUCCEEDED,
    )
    workspaces.create(due.task_id)
    remove = workspaces.remove
    attempts = 0

    def busy_once(identifier: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("file busy")
        remove(identifier)

    monkeypatch.setattr(workspaces, "remove", busy_once)
    cleanup = TaskCleanupService(repository, workspaces, clock=lambda: now)
    cleanup.expire_due()
    assert repository.list_due_for_expiry(now) == [due]
    cleanup.expire_due()
    assert repository.list_due_for_expiry(now) == []
    assert workspaces.list_task_ids() == ()


def test_success_cleanup_preserves_only_result(tmp_path: Path) -> None:
    workspaces = TaskWorkspaceStore(tmp_path / "tasks")
    identifier = task_id("success-assets")
    workspace = workspaces.create(identifier)
    (workspace / "source.png").write_bytes(b"source")
    (workspace / "target.jpg").write_bytes(b"target")
    (workspace / "result.png").write_bytes(b"result")

    workspaces.remove_inputs(identifier)

    assert [path.name for path in workspace.iterdir()] == ["result.png"]


def test_startup_permission_failures_are_retried_without_deleting_new_uploads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(logging.getLogger("localface"), "propagate", True)
    caplog.set_level(logging.WARNING, logger="localface")

    async def scenario() -> None:
        now = datetime.now(UTC)
        repository = SqliteTaskRepository(tmp_path / "tasks.sqlite3")
        repository.initialize()
        workspaces = TaskWorkspaceStore(tmp_path / "tasks")
        abandoned = create_task(
            repository,
            identifier=task_id("abandoned"),
            created_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=25),
            status=TaskStatus.RUNNING,
        )
        orphan = task_id("orphan-busy")
        for identifier in (abandoned.task_id, orphan):
            workspaces.create(identifier)
        remove = workspaces.remove
        locked = True
        remaining = {abandoned.task_id, orphan}
        cleaned = asyncio.Event()

        def remove_when_unlocked(identifier: str) -> None:
            if locked:
                raise PermissionError("private path must not appear in logs")
            remove(identifier)
            remaining.discard(identifier)
            if not remaining:
                cleaned.set()

        monkeypatch.setattr(workspaces, "remove", remove_when_unlocked)
        cleanup = TaskCleanupService(repository, workspaces, clock=lambda: now)
        cleanup.recover_startup()
        task = repository.get_for_actor(abandoned.task_id, abandoned.actor_id)
        assert task is not None and task.status is TaskStatus.TIMED_OUT
        assert len(workspaces.list_task_ids()) == 2
        assert "startup_cleanup_retry" in caplog.text
        assert "private path" not in caplog.text

        # A newly uploading file can legitimately precede its task DB record.
        fresh = task_id("new-upload-in-flight")
        workspaces.create(fresh)
        locked = False
        stop = asyncio.Event()
        worker = asyncio.create_task(cleanup.run_periodically(stop, interval_seconds=0.01))
        try:
            await asyncio.wait_for(cleaned.wait(), timeout=3)
        finally:
            stop.set()
            await worker
        assert workspaces.list_task_ids() == (fresh,)

    asyncio.run(scenario())


def test_startup_does_not_mark_expired_until_bytes_are_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    repository = SqliteTaskRepository(tmp_path / "tasks.sqlite3")
    repository.initialize()
    workspaces = TaskWorkspaceStore(tmp_path / "tasks")
    due = create_task(
        repository,
        identifier=task_id("startup-expiry-busy"),
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        status=TaskStatus.SUCCEEDED,
    )
    workspaces.create(due.task_id)
    remove = workspaces.remove

    def locked(identifier: str) -> None:
        raise PermissionError("busy")

    monkeypatch.setattr(workspaces, "remove", locked)
    TaskCleanupService(repository, workspaces, clock=lambda: now).recover_startup()
    assert repository.list_due_for_expiry(now) == [due]
    monkeypatch.setattr(workspaces, "remove", remove)
    TaskCleanupService(repository, workspaces, clock=lambda: now).recover_startup()
    assert repository.list_due_for_expiry(now) == []
    assert workspaces.list_task_ids() == ()
