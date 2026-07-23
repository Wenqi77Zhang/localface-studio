"""SQLite implementation of the minimal task metadata repository."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Row

from localface_studio.application.task_repository import (
    ConcurrentTaskUpdateError,
    DuplicateTaskError,
)
from localface_studio.domain.tasks import OutputFormat, TaskRecord, TaskStatus, WorkflowNode


class SqliteTaskRepository:
    """Persist task metadata in a local database without image bytes or paths."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        """Create the parent directory, schema, and expiry lookup index."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consent_version TEXT NOT NULL,
                    consented_at TEXT NOT NULL,
                    output_format TEXT NOT NULL,
                    watermark_enabled INTEGER NOT NULL CHECK (watermark_enabled IN (0, 1)),
                    version INTEGER NOT NULL CHECK (version >= 0),
                    current_node TEXT,
                    error_code TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_actor_status
                    ON tasks(actor_id, status);
                CREATE INDEX IF NOT EXISTS idx_tasks_status_expiry
                    ON tasks(status, expires_at);
                """
            )

    def create(self, task: TaskRecord) -> None:
        """Insert a new task, mapping identifier collisions to a stable exception."""
        if task.status is not TaskStatus.QUEUED or task.version != 0:
            raise ValueError("new tasks must start queued at version zero")
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id, actor_id, status, created_at, updated_at, expires_at,
                        consent_version, consented_at, output_format, watermark_enabled,
                        version, current_node, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._values(task),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateTaskError("task identifier already exists") from error

    def get_for_actor(self, task_id: str, actor_id: str) -> TaskRecord | None:
        """Fetch by task and owner together so callers cannot bypass isolation."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ? AND actor_id = ?",
                (task_id, actor_id),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def save(self, task: TaskRecord, *, expected_version: int) -> None:
        """Update all mutable fields with an atomic optimistic-version check."""
        if task.version != expected_version + 1:
            raise ValueError("saved task version must increment by exactly one")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET
                    status = ?,
                    updated_at = ?,
                    expires_at = ?,
                    output_format = ?,
                    watermark_enabled = ?,
                    version = ?,
                    current_node = ?,
                    error_code = ?
                WHERE task_id = ? AND actor_id = ? AND version = ?
                """,
                (
                    task.status.value,
                    task.updated_at.isoformat(),
                    task.expires_at.isoformat(),
                    task.output_format.value,
                    int(task.watermark_enabled),
                    task.version,
                    task.current_node.value if task.current_node is not None else None,
                    task.error_code,
                    task.task_id,
                    task.actor_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrentTaskUpdateError("task revision is stale or unavailable")

    def count_unfinished_for_actor(self, actor_id: str) -> int:
        """Count tasks that consume the per-session queue allowance."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM tasks
                WHERE actor_id = ? AND status IN (?, ?)
                """,
                (actor_id, TaskStatus.QUEUED.value, TaskStatus.RUNNING.value),
            ).fetchone()
        if row is None:
            return 0
        return int(row["total"])

    def list_due_for_expiry(self, at: datetime) -> list[TaskRecord]:
        """List only successful results whose explicit retention time has elapsed."""
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("expiry time must be timezone-aware")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM tasks
                WHERE status = ? AND expires_at <= ?
                ORDER BY expires_at, task_id
                """,
                (TaskStatus.SUCCEEDED.value, at.isoformat()),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_all(self) -> list[TaskRecord]:
        """List minimal records in stable order for startup recovery."""
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at, task_id").fetchall()
        return [self._from_row(row) for row in rows]

    def _connect(self) -> Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _values(task: TaskRecord) -> tuple[object, ...]:
        return (
            task.task_id,
            task.actor_id,
            task.status.value,
            task.created_at.isoformat(),
            task.updated_at.isoformat(),
            task.expires_at.isoformat(),
            task.consent_version,
            task.consented_at.isoformat(),
            task.output_format.value,
            int(task.watermark_enabled),
            task.version,
            task.current_node.value if task.current_node is not None else None,
            task.error_code,
        )

    @staticmethod
    def _from_row(row: Row) -> TaskRecord:
        current_node = row["current_node"]
        return TaskRecord(
            task_id=str(row["task_id"]),
            actor_id=str(row["actor_id"]),
            status=TaskStatus(str(row["status"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            expires_at=datetime.fromisoformat(str(row["expires_at"])),
            consent_version=str(row["consent_version"]),
            consented_at=datetime.fromisoformat(str(row["consented_at"])),
            output_format=OutputFormat(str(row["output_format"])),
            watermark_enabled=bool(row["watermark_enabled"]),
            version=int(row["version"]),
            current_node=WorkflowNode(str(current_node)) if current_node is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        )
