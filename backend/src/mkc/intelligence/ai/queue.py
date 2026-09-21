"""Simple in-memory task queue for AI operations.

Can evolve to Celery/RQ for production use.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

logger = logging.getLogger("mkc.ai.queue")


class TaskStatus(Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Task:
    """A queued AI task."""
    id: str = field(default_factory=lambda: str(uuid4()))
    task_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


class TaskQueue:
    """Simple in-memory task queue with priority and retry logic."""

    def __init__(self):
        self._queue: list[Task] = []
        self._running: dict[str, Task] = {}
        self._completed: dict[str, Task] = {}
        self._lock = threading.Lock()

    def enqueue(self, task_type: str, payload: dict[str, Any], 
                priority: TaskPriority = TaskPriority.NORMAL,
                max_retries: int = 3) -> Task:
        """Add a task to the queue."""
        task = Task(
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_retries=max_retries
        )
        with self._lock:
            self._queue.append(task)
            self._queue.sort(key=lambda t: t.priority.value, reverse=True)
        logger.info(f"Task enqueued: {task.id} ({task_type}, priority={priority.name})")
        return task

    def dequeue(self) -> Optional[Task]:
        """Get the next task to run."""
        with self._lock:
            if self._queue:
                task = self._queue.pop(0)
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.utcnow()
                self._running[task.id] = task
                return task
        return None

    def complete(self, task_id: str, result: Any) -> None:
        """Mark a task as completed."""
        with self._lock:
            if task_id in self._running:
                task = self._running.pop(task_id)
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                task.result = result
                self._completed[task_id] = task
                logger.info(f"Task completed: {task_id}")

    def fail(self, task_id: str, error: str) -> None:
        """Mark a task as failed or retry."""
        with self._lock:
            if task_id in self._running:
                task = self._running.pop(task_id)
                task.error = error
                task.retry_count += 1
                
                if task.retry_count < task.max_retries:
                    # Retry with exponential backoff
                    task.status = TaskStatus.PENDING
                    task.started_at = None
                    # Note: sleep should be handled by the worker, not here
                    logger.warning(f"Task {task_id} failed, retry {task.retry_count}/{task.max_retries}")
                    self._queue.append(task)
                    self._queue.sort(key=lambda t: t.priority.value, reverse=True)
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.utcnow()
                    self._completed[task_id] = task
                    logger.error(f"Task failed permanently: {task_id} after {task.max_retries} retries")

    def get_status(self, task_id: str) -> Optional[Task]:
        """Get task status."""
        with self._lock:
            if task_id in self._running:
                return self._running[task_id]
            if task_id in self._completed:
                return self._completed[task_id]
            for task in self._queue:
                if task.id == task_id:
                    return task
        return None

    def get_queue_status(self) -> dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            return {
                "pending": len(self._queue),
                "running": len(self._running),
                "completed": len(self._completed),
            }


# Global task queue instance
_global_queue: Optional[TaskQueue] = None


def get_queue() -> TaskQueue:
    """Get the global task queue instance."""
    global _global_queue
    if _global_queue is None:
        _global_queue = TaskQueue()
    return _global_queue
