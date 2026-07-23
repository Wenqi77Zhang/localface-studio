"""Single-concurrency task execution, cancellation, timeout, and event history."""

import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from localface_studio.application.task_creation import utc_now
from localface_studio.application.task_repository import TaskRepository
from localface_studio.domain.tasks import (
    TaskRecord,
    TaskStatus,
    WorkflowNode,
    advance_task_node,
    transition_task,
)

TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.TIMED_OUT,
        TaskStatus.EXPIRED,
        TaskStatus.DELETED,
    }
)


class WorkflowExecutionError(RuntimeError):
    """Expected backend failure with a stable non-sensitive error code."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


NodeReporter = Callable[[WorkflowNode], Awaitable[None]]


class WorkflowBackend(Protocol):
    """Replaceable image workflow boundary used later by native and ComfyUI backends."""

    async def run(self, task: TaskRecord, report_node: NodeReporter) -> None:
        """Produce a valid result or raise without mutating task metadata."""
        ...


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Privacy-safe task snapshot suitable for a future SSE payload."""

    task_id: str
    version: int
    status: TaskStatus
    current_node: WorkflowNode | None
    updated_at: datetime
    error_code: str | None

    @classmethod
    def from_record(cls, task: TaskRecord) -> TaskEvent:
        return cls(
            task_id=task.task_id,
            version=task.version,
            status=task.status,
            current_node=task.current_node,
            updated_at=task.updated_at,
            error_code=task.error_code,
        )


class TaskEventBroker:
    """Keep bounded event history and fan out live updates without persistence."""

    def __init__(self, *, history_size: int = 64, subscriber_size: int = 64) -> None:
        if min(history_size, subscriber_size) < 1:
            raise ValueError("event buffer sizes must be positive")
        self._history_size = history_size
        self._subscriber_size = subscriber_size
        self._history: dict[str, deque[TaskEvent]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[TaskEvent]]] = defaultdict(set)

    def publish(self, task: TaskRecord) -> TaskEvent:
        event = TaskEvent.from_record(task)
        history = self._history.setdefault(task.task_id, deque(maxlen=self._history_size))
        history.append(event)
        for subscriber in tuple(self._subscribers[task.task_id]):
            if subscriber.full():
                subscriber.get_nowait()
            subscriber.put_nowait(event)
        return event

    def history(self, task_id: str, *, after_version: int = -1) -> tuple[TaskEvent, ...]:
        return tuple(
            event for event in self._history.get(task_id, ()) if event.version > after_version
        )

    @asynccontextmanager
    async def subscribe(self, task_id: str) -> AsyncIterator[asyncio.Queue[TaskEvent]]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=self._subscriber_size)
        self._subscribers[task_id].add(queue)
        try:
            yield queue
        finally:
            subscribers = self._subscribers[task_id]
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(task_id, None)


@dataclass(frozen=True, slots=True)
class QueueItem:
    task_id: str
    actor_id: str


class SingleTaskQueue:
    """Run one backend task at a time and make every terminal path explicit."""

    def __init__(
        self,
        repository: TaskRepository,
        backend: WorkflowBackend,
        events: TaskEventBroker,
        cleanup: Callable[[str], None],
        *,
        timeout_seconds: float = 120,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._repository = repository
        self._backend = backend
        self._events = events
        self._cleanup = cleanup
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._items: asyncio.Queue[QueueItem | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._cancellations: dict[str, asyncio.Event] = {}

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._work(), name="localface-task-worker")

    async def stop(self) -> None:
        if self._worker is None:
            return
        await self._items.put(None)
        await self._worker
        self._worker = None

    async def enqueue(self, task: TaskRecord) -> None:
        if self._worker is None:
            raise RuntimeError("task queue is not running")
        if task.status is not TaskStatus.QUEUED:
            raise ValueError("only queued tasks can be enqueued")
        self._events.publish(task)
        await self._items.put(QueueItem(task.task_id, task.actor_id))

    async def cancel(self, task_id: str, actor_id: str) -> TaskRecord | None:
        task = self._repository.get_for_actor(task_id, actor_id)
        if task is None:
            return None
        if task.status is TaskStatus.QUEUED:
            cancelled = transition_task(task, TaskStatus.CANCELLED, at=self._clock())
            self._repository.save(cancelled, expected_version=task.version)
            self._cleanup(task_id)
            self._events.publish(cancelled)
            return cancelled
        if task.status is TaskStatus.RUNNING:
            cancellation = self._cancellations.get(task_id)
            if cancellation is not None:
                cancellation.set()
            return task
        return task

    async def _work(self) -> None:
        while (item := await self._items.get()) is not None:
            try:
                await self._execute(item)
            finally:
                self._items.task_done()
        self._items.task_done()

    async def _execute(self, item: QueueItem) -> None:
        queued = self._repository.get_for_actor(item.task_id, item.actor_id)
        if queued is None or queued.status is not TaskStatus.QUEUED:
            return
        current = transition_task(queued, TaskStatus.RUNNING, at=self._clock())
        self._repository.save(current, expected_version=queued.version)
        self._events.publish(current)
        cancellation = asyncio.Event()
        self._cancellations[item.task_id] = cancellation

        async def report_node(node: WorkflowNode) -> None:
            nonlocal current
            updated = advance_task_node(current, node, at=self._clock())
            self._repository.save(updated, expected_version=current.version)
            current = updated
            self._events.publish(current)

        runner = asyncio.create_task(self._backend.run(current, report_node))
        cancellation_waiter = asyncio.create_task(cancellation.wait())
        final_status = TaskStatus.SUCCEEDED
        error_code: str | None = None
        try:
            done, _ = await asyncio.wait(
                {runner, cancellation_waiter},
                timeout=self._timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation_waiter in done:
                final_status = TaskStatus.CANCELLED
            elif runner not in done:
                final_status = TaskStatus.TIMED_OUT
            else:
                await runner
        except WorkflowExecutionError as error:
            final_status = TaskStatus.FAILED
            error_code = error.error_code
        except asyncio.CancelledError:
            final_status = TaskStatus.FAILED
            error_code = "workflow_cancelled_unexpectedly"
        except Exception:
            final_status = TaskStatus.FAILED
            error_code = "internal_workflow_error"
        finally:
            for pending in (runner, cancellation_waiter):
                if not pending.done():
                    pending.cancel()
                    with suppress(asyncio.CancelledError):
                        await pending
            self._cancellations.pop(item.task_id, None)

        finished = transition_task(
            current,
            final_status,
            at=self._clock(),
            current_node=current.current_node,
            error_code=error_code,
        )
        self._repository.save(finished, expected_version=current.version)
        if final_status is not TaskStatus.SUCCEEDED:
            self._cleanup(item.task_id)
        self._events.publish(finished)
