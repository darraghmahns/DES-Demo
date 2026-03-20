"""Background extraction task manager.

Runs extraction pipelines as detached asyncio tasks so they survive
browser disconnects. Each task has a unique ID and stores SSE events
in memory for reconnectable streaming.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TASK_TTL_SECONDS = 3600  # 1 hour — completed tasks older than this are pruned
MAX_COMPLETED_TASKS = 50  # hard cap on completed/errored tasks in memory


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ExtractionTask:
    """Tracks a single background extraction."""

    task_id: str
    mode: str
    filename: str
    status: TaskStatus = TaskStatus.PENDING
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = field(default=None)
    _waiters: list[asyncio.Event] = field(default_factory=list, repr=False)
    _asyncio_task: asyncio.Task | None = field(default=None, repr=False)

    def append_event(self, event: dict[str, Any]) -> None:
        """Add an event and wake all waiting SSE streams."""
        self.events.append(event)
        for waiter in self._waiters:
            waiter.set()

    def mark_complete(self, status: TaskStatus) -> None:
        """Mark task as completed/errored and record the timestamp."""
        self.status = status
        self.completed_at = datetime.now(timezone.utc)

    def add_waiter(self) -> asyncio.Event:
        """Register a new waiter that will be notified on new events."""
        ev = asyncio.Event()
        self._waiters.append(ev)
        return ev

    def remove_waiter(self, ev: asyncio.Event) -> None:
        """Remove a waiter when the SSE stream disconnects."""
        try:
            self._waiters.remove(ev)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Global task registry
# ---------------------------------------------------------------------------

_tasks: dict[str, ExtractionTask] = {}


def create_task(mode: str, filename: str, metadata: dict[str, Any] | None = None) -> ExtractionTask:
    """Create a new extraction task (does not start it yet)."""
    task_id = uuid.uuid4().hex[:12]
    task = ExtractionTask(task_id=task_id, mode=mode, filename=filename, metadata=metadata or {})
    _tasks[task_id] = task
    return task


def get_task(task_id: str) -> ExtractionTask | None:
    """Look up a task by ID."""
    return _tasks.get(task_id)


def get_active_task(mode: str, filename: str) -> ExtractionTask | None:
    """Find a running/pending task for this file and mode (avoid duplicates)."""
    for task in _tasks.values():
        if (
            task.mode == mode
            and task.filename == filename
            and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ):
            return task
    return None


def list_tasks() -> list[dict[str, Any]]:
    """Return summary of all tasks."""
    return [
        {
            "task_id": t.task_id,
            "mode": t.mode,
            "filename": t.filename,
            "status": t.status.value,
            "event_count": len(t.events),
            "created_at": t.created_at.isoformat(),
            "transaction_id": t.metadata.get("transaction_id"),
            "upload_job_id": t.metadata.get("upload_job_id"),
            "display_filename": t.metadata.get("display_filename") or t.filename,
        }
        for t in _tasks.values()
    ]


def cleanup_old_tasks(
    max_completed: int = MAX_COMPLETED_TASKS,
    ttl_seconds: int = TASK_TTL_SECONDS,
) -> None:
    """Remove old completed/errored tasks using TTL + count cap.

    Two-pass cleanup:
      1. Remove any finished task older than *ttl_seconds*.
      2. If still over *max_completed*, remove oldest by completion time.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=ttl_seconds)

    finished = [
        t for t in _tasks.values()
        if t.status in (TaskStatus.COMPLETE, TaskStatus.ERROR)
    ]

    # Pass 1: TTL-based removal
    expired_ids = [
        t.task_id for t in finished
        if (t.completed_at or t.created_at) < cutoff
    ]
    for tid in expired_ids:
        del _tasks[tid]

    if expired_ids:
        log.debug("Cleaned up %d expired tasks (TTL=%ds)", len(expired_ids), ttl_seconds)

    # Pass 2: count cap
    remaining = [
        t for t in _tasks.values()
        if t.status in (TaskStatus.COMPLETE, TaskStatus.ERROR)
    ]
    remaining.sort(key=lambda t: t.completed_at or t.created_at)
    while len(remaining) > max_completed:
        old = remaining.pop(0)
        del _tasks[old.task_id]
