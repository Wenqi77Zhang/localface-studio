"""Single-concurrency queue, event, cancellation, failure, and timeout tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from localface_studio.application.task_queue import (
    NodeReporter,
    SingleTaskQueue,
    TaskEventBroker,
    WorkflowExecutionError,
)
from localface_studio.domain.tasks import (
    OutputFormat,
    TaskRecord,
    TaskStatus,
    WorkflowNode,
)
from localface_studio.infrastructure.sqlite_tasks import SqliteTaskRepository


def make_task(task_id: str, actor_id: str = "actor-one") -> TaskRecord:
    now = datetime.now(UTC)
    return TaskRecord(
        task_id=task_id,
        actor_id=actor_id,
        status=TaskStatus.QUEUED,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        consent_version="2026-07-23-v1",
        consented_at=now,
        output_format=OutputFormat.PNG,
        watermark_enabled=True,
    )


def make_repository(tmp_path: Path) -> SqliteTaskRepository:
    repository = SqliteTaskRepository(tmp_path / "tasks.sqlite3")
    repository.initialize()
    return repository


class TrackingBackend:
    def __init__(self) -> None:
        self.active = 0
        self.maximum_active = 0

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            for node in WorkflowNode:
                await report_node(node)
                await asyncio.sleep(0)
        finally:
            self.active -= 1


class FailingBackend:
    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        await report_node(WorkflowNode.VALIDATE)
        raise WorkflowExecutionError("controlled_failure")


class BlockingBackend:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        await report_node(WorkflowNode.VALIDATE)
        self.started.set()
        await self.release.wait()


def test_queue_runs_tasks_one_at_a_time_and_publishes_ordered_events(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = make_repository(tmp_path)
        first = make_task("first-task")
        second = make_task("second-task")
        repository.create(first)
        repository.create(second)
        backend = TrackingBackend()
        events = TaskEventBroker()
        queue = SingleTaskQueue(repository, backend, events, lambda task_id: None)

        queue.start()
        await queue.enqueue(first)
        await queue.enqueue(second)
        await queue.stop()

        first_result = repository.get_for_actor(first.task_id, first.actor_id)
        second_result = repository.get_for_actor(second.task_id, second.actor_id)
        assert first_result is not None and first_result.status is TaskStatus.SUCCEEDED
        assert second_result is not None and second_result.status is TaskStatus.SUCCEEDED
        assert backend.maximum_active == 1
        first_history = events.history(first.task_id)
        assert [event.version for event in first_history] == list(
            range(first_history[-1].version + 1)
        )
        assert first_history[-1].current_node is WorkflowNode.EXPORT

    asyncio.run(scenario())


def test_failure_and_timeout_are_terminal_and_cleanup_files(tmp_path: Path) -> None:
    async def run_case(
        task_id: str,
        backend: FailingBackend | BlockingBackend,
        timeout: float,
    ) -> tuple[TaskRecord, list[str]]:
        repository = make_repository(tmp_path / task_id)
        task = make_task(task_id)
        repository.create(task)
        cleaned: list[str] = []
        queue = SingleTaskQueue(
            repository,
            backend,
            TaskEventBroker(),
            cleaned.append,
            timeout_seconds=timeout,
        )
        queue.start()
        await queue.enqueue(task)
        await queue.stop()
        result = repository.get_for_actor(task.task_id, task.actor_id)
        assert result is not None
        return result, cleaned

    async def scenario() -> None:
        failed, failed_cleanup = await run_case("failed-task", FailingBackend(), 1)
        timed_out, timeout_cleanup = await run_case("timeout-task", BlockingBackend(), 0.01)

        assert failed.status is TaskStatus.FAILED
        assert failed.error_code == "controlled_failure"
        assert failed_cleanup == ["failed-task"]
        assert timed_out.status is TaskStatus.TIMED_OUT
        assert timeout_cleanup == ["timeout-task"]

    asyncio.run(scenario())


def test_running_and_queued_tasks_can_be_cancelled(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = make_repository(tmp_path)
        running_task = make_task("running-task")
        queued_task = make_task("queued-task")
        repository.create(running_task)
        repository.create(queued_task)
        backend = BlockingBackend()
        cleaned: list[str] = []
        queue = SingleTaskQueue(
            repository,
            backend,
            TaskEventBroker(),
            cleaned.append,
            timeout_seconds=1,
        )
        queue.start()
        await queue.enqueue(running_task)
        await backend.started.wait()

        cancellation_requested = await queue.cancel(running_task.task_id, running_task.actor_id)
        backend.release.set()
        queued_cancelled = await queue.cancel(queued_task.task_id, queued_task.actor_id)
        await queue.stop()

        running_result = repository.get_for_actor(running_task.task_id, running_task.actor_id)
        assert cancellation_requested is not None
        assert cancellation_requested.status is TaskStatus.RUNNING
        assert running_result is not None and running_result.status is TaskStatus.CANCELLED
        assert queued_cancelled is not None and queued_cancelled.status is TaskStatus.CANCELLED
        assert set(cleaned) == {"running-task", "queued-task"}
        assert await queue.cancel("missing", running_task.actor_id) is None

    asyncio.run(scenario())


def test_event_broker_bounds_history_and_unregisters_subscribers() -> None:
    async def scenario() -> None:
        broker = TaskEventBroker(history_size=2, subscriber_size=1)
        task = make_task("event-task")
        async with broker.subscribe(task.task_id) as subscriber:
            broker.publish(task)
            broker.publish(task)
            received = await subscriber.get()
            assert received.task_id == task.task_id
        assert len(broker.history(task.task_id)) == 2

    asyncio.run(scenario())
