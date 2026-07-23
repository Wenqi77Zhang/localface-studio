"""Task contracts and state-transition rules independent of API and storage."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from secrets import token_urlsafe


class TaskStatus(StrEnum):
    """Stable task states shared by API, workers, storage, and the frontend."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    EXPIRED = "expired"
    DELETED = "deleted"


class WorkflowNode(StrEnum):
    """Phase 2 workflow nodes; later backends may add their own versioned graph."""

    VALIDATE = "validate"
    PREPARE = "prepare"
    SIMULATE = "simulate"
    INSPECT = "inspect"
    EXPORT = "export"


class OutputFormat(StrEnum):
    """Supported phase 2 output encodings."""

    PNG = "png"
    JPEG = "jpeg"


class RetentionOption(StrEnum):
    """User-selectable result retention periods with a 24-hour hard maximum."""

    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    THREE_HOURS = "3h"
    SIX_HOURS = "6h"
    TWELVE_HOURS = "12h"
    ONE_DAY = "24h"

    @property
    def duration(self) -> timedelta:
        return {
            RetentionOption.THIRTY_MINUTES: timedelta(minutes=30),
            RetentionOption.ONE_HOUR: timedelta(hours=1),
            RetentionOption.THREE_HOURS: timedelta(hours=3),
            RetentionOption.SIX_HOURS: timedelta(hours=6),
            RetentionOption.TWELVE_HOURS: timedelta(hours=12),
            RetentionOption.ONE_DAY: timedelta(days=1),
        }[self]


class InvalidTaskTransition(ValueError):
    """Raised when a caller attempts a transition outside the frozen state graph."""


_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMED_OUT,
        }
    ),
    TaskStatus.SUCCEEDED: frozenset({TaskStatus.EXPIRED, TaskStatus.DELETED}),
    TaskStatus.FAILED: frozenset({TaskStatus.DELETED}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.DELETED}),
    TaskStatus.TIMED_OUT: frozenset({TaskStatus.DELETED}),
    TaskStatus.EXPIRED: frozenset({TaskStatus.DELETED}),
    TaskStatus.DELETED: frozenset(),
}
_NODE_ORDER = {node: index for index, node in enumerate(WorkflowNode)}


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Minimal task metadata; image bytes and local paths are deliberately excluded."""

    task_id: str
    actor_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    consent_version: str
    consented_at: datetime
    output_format: OutputFormat
    watermark_enabled: bool
    jpeg_quality: int = 95
    version: int = 0
    current_node: WorkflowNode | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("task_id", "actor_id", "consent_version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")
        for field_name in ("created_at", "updated_at", "expires_at", "consented_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if self.version < 0:
            raise ValueError("version must not be negative")
        if type(self.jpeg_quality) is not int or not 5 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be an integer from 5 to 100")
        if self.error_code is not None and not self.error_code.strip():
            raise ValueError("error_code must be absent or non-blank")
        if self.status is TaskStatus.FAILED and self.error_code is None:
            raise ValueError("failed tasks require a stable error_code")
        if self.status is not TaskStatus.FAILED and self.error_code is not None:
            raise ValueError("error_code is only allowed for failed tasks")


def new_task_id() -> str:
    """Return an unpredictable URL-safe identifier with at least 192 bits of entropy."""
    return token_urlsafe(24)


def transition_task(
    task: TaskRecord,
    target: TaskStatus,
    *,
    at: datetime,
    current_node: WorkflowNode | None = None,
    error_code: str | None = None,
) -> TaskRecord:
    """Create the next immutable task revision after validating the state graph."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("transition time must be timezone-aware")
    if at < task.updated_at:
        raise ValueError("transition time must not precede the last update")
    if target not in _ALLOWED_TRANSITIONS[task.status]:
        raise InvalidTaskTransition(f"cannot transition from {task.status} to {target}")
    return replace(
        task,
        status=target,
        updated_at=at,
        current_node=current_node,
        error_code=error_code,
        version=task.version + 1,
    )


def advance_task_node(task: TaskRecord, node: WorkflowNode, *, at: datetime) -> TaskRecord:
    """Advance a running task through the versioned workflow without changing status."""
    if task.status is not TaskStatus.RUNNING:
        raise InvalidTaskTransition("workflow nodes can only advance while a task is running")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("node update time must be timezone-aware")
    if at < task.updated_at:
        raise ValueError("node update time must not precede the last update")
    if task.current_node is not None and _NODE_ORDER[node] <= _NODE_ORDER[task.current_node]:
        raise InvalidTaskTransition("workflow nodes must advance in order")
    return replace(
        task,
        current_node=node,
        updated_at=at,
        version=task.version + 1,
    )
