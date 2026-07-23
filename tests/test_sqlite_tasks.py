"""SQLite task persistence, isolation, expiry, and concurrency tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from localface_studio.application.task_repository import (
    ConcurrentTaskUpdateError,
    DuplicateTaskError,
    TaskRepository,
)
from localface_studio.domain.tasks import (
    OutputFormat,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
    transition_task,
)
from localface_studio.infrastructure.sqlite_tasks import SqliteTaskRepository


def make_task(*, task_id: str = "task-one", actor_id: str = "actor-one") -> TaskRecord:
    created_at = datetime(2026, 7, 23, 8, tzinfo=UTC)
    return TaskRecord(
        task_id=task_id,
        actor_id=actor_id,
        status=TaskStatus.QUEUED,
        created_at=created_at,
        updated_at=created_at,
        expires_at=created_at + timedelta(minutes=30),
        consent_version="2026-07-23",
        consented_at=created_at,
        output_format=OutputFormat.PNG,
        watermark_enabled=True,
    )


def make_repository(tmp_path: Path) -> SqliteTaskRepository:
    repository = SqliteTaskRepository(tmp_path / "runtime" / "tasks.sqlite3")
    repository.initialize()
    return repository


def accepts_repository_contract(repository: TaskRepository) -> TaskRepository:
    """Make static checking verify that SQLite satisfies the application protocol."""
    return repository


def test_create_read_and_actor_isolation(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    task = make_task()
    repository.create(task)

    stored = repository.get_for_actor(task.task_id, task.actor_id)

    assert stored == task
    assert repository.get_for_actor(task.task_id, "different-actor") is None
    assert accepts_repository_contract(repository) is repository


def test_duplicate_identifier_is_reported_without_database_details(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    task = make_task()
    repository.create(task)

    with pytest.raises(DuplicateTaskError, match="already exists"):
        repository.create(task)


def test_create_and_save_enforce_revision_invariants(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    queued = make_task()

    with pytest.raises(ValueError, match="version zero"):
        repository.create(transition_task(queued, TaskStatus.RUNNING, at=queued.updated_at))

    repository.create(queued)
    running = transition_task(queued, TaskStatus.RUNNING, at=queued.updated_at)
    with pytest.raises(ValueError, match="exactly one"):
        repository.save(running, expected_version=running.version)


def test_optimistic_update_prevents_stale_cancellation(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    queued = make_task()
    repository.create(queued)
    running = transition_task(
        queued,
        TaskStatus.RUNNING,
        at=queued.updated_at + timedelta(seconds=1),
        current_node=WorkflowNode.VALIDATE,
    )
    repository.save(running, expected_version=queued.version)

    stale_cancellation = transition_task(
        queued,
        TaskStatus.CANCELLED,
        at=queued.updated_at + timedelta(seconds=1),
    )
    with pytest.raises(ConcurrentTaskUpdateError, match="stale"):
        repository.save(stale_cancellation, expected_version=queued.version)

    assert repository.get_for_actor(queued.task_id, queued.actor_id) == running


def test_unfinished_count_and_due_expiry_only_include_relevant_tasks(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    queued = make_task(task_id="queued")
    successful_source = make_task(task_id="successful")
    repository.create(queued)
    repository.create(successful_source)

    running = transition_task(
        successful_source,
        TaskStatus.RUNNING,
        at=successful_source.created_at + timedelta(seconds=1),
    )
    repository.save(running, expected_version=successful_source.version)
    succeeded = transition_task(
        running,
        TaskStatus.SUCCEEDED,
        at=running.updated_at + timedelta(seconds=1),
        current_node=WorkflowNode.EXPORT,
    )
    repository.save(succeeded, expected_version=running.version)

    assert repository.count_unfinished_for_actor(queued.actor_id) == 1
    assert repository.list_due_for_expiry(queued.created_at + timedelta(minutes=29)) == []
    assert repository.list_due_for_expiry(queued.created_at + timedelta(minutes=31)) == [succeeded]


def test_expiry_query_requires_timezone_aware_time(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    task = make_task()

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.list_due_for_expiry(task.created_at.replace(tzinfo=None))
