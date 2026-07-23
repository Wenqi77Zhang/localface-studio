"""Task state-machine and identifier tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from localface_studio.domain.tasks import (
    InvalidTaskTransition,
    OutputFormat,
    RetentionOption,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
    new_task_id,
    transition_task,
)


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


def test_task_identifier_is_unpredictable_and_url_safe() -> None:
    first = new_task_id()
    second = new_task_id()

    assert first != second
    assert len(first) >= 32
    assert all(character.isalnum() or character in "-_" for character in first)


def test_valid_state_transitions_create_new_revisions() -> None:
    queued = make_task()
    running_at = queued.created_at + timedelta(seconds=1)
    running = transition_task(
        queued,
        TaskStatus.RUNNING,
        at=running_at,
        current_node=WorkflowNode.VALIDATE,
    )
    succeeded = transition_task(
        running,
        TaskStatus.SUCCEEDED,
        at=running_at + timedelta(seconds=1),
        current_node=WorkflowNode.EXPORT,
    )

    assert queued.status is TaskStatus.QUEUED
    assert running.status is TaskStatus.RUNNING
    assert running.version == 1
    assert succeeded.status is TaskStatus.SUCCEEDED
    assert succeeded.version == 2


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TaskStatus.QUEUED, TaskStatus.SUCCEEDED),
        (TaskStatus.SUCCEEDED, TaskStatus.RUNNING),
        (TaskStatus.DELETED, TaskStatus.QUEUED),
    ],
)
def test_invalid_state_transitions_are_rejected(
    source: TaskStatus,
    target: TaskStatus,
) -> None:
    task = replace(make_task(), status=source)

    with pytest.raises(InvalidTaskTransition, match="cannot transition"):
        transition_task(task, target, at=task.updated_at)


def test_failed_state_requires_stable_error_code() -> None:
    running = replace(make_task(), status=TaskStatus.RUNNING)

    with pytest.raises(ValueError, match="error_code"):
        transition_task(running, TaskStatus.FAILED, at=running.updated_at)

    failed = transition_task(
        running,
        TaskStatus.FAILED,
        at=running.updated_at,
        error_code="simulation_failed",
    )
    assert failed.error_code == "simulation_failed"

    with pytest.raises(ValueError, match="only allowed"):
        replace(make_task(), error_code="unexpected")


def test_task_times_must_be_timezone_aware_and_monotonic() -> None:
    task = make_task()
    naive = datetime(2026, 7, 23, 8)

    with pytest.raises(ValueError, match="timezone-aware"):
        replace(task, updated_at=naive)
    with pytest.raises(ValueError, match="must not precede"):
        transition_task(
            task,
            TaskStatus.RUNNING,
            at=task.updated_at - timedelta(seconds=1),
        )


@pytest.mark.parametrize("quality", [4, 101, 95.0, True])
def test_jpeg_quality_must_be_a_bounded_integer(quality: object) -> None:
    with pytest.raises(ValueError, match="jpeg_quality"):
        replace(make_task(), jpeg_quality=quality)  # type: ignore[arg-type]


def test_retention_options_stop_at_24_hours() -> None:
    assert [option.value for option in RetentionOption] == [
        "30m",
        "1h",
        "3h",
        "6h",
        "12h",
        "24h",
    ]
    assert max(option.duration for option in RetentionOption) == timedelta(hours=24)
