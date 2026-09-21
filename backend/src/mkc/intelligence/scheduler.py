"""Scheduler for running research tasks on a schedule."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from uuid import uuid4

logger = logging.getLogger("mkc.intelligence.scheduler")


@dataclass
class ScheduledTask:
    """A scheduled task definition."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    task_type: str = ""
    schedule: str = ""  # cron expression
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class SimpleScheduler:
    """Simple in-memory scheduler for research tasks.
    
    Note: This is a basic implementation. For production use, consider:
    - APScheduler for robust cron scheduling
    - Celery Beat for distributed task scheduling
    - System cron jobs calling the CLI
    """

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False

    def add_task(self, name: str, task_type: str, schedule: str, metadata: dict[str, Any] = None) -> ScheduledTask:
        """Add a scheduled task."""
        task = ScheduledTask(
            name=name,
            task_type=task_type,
            schedule=schedule,
            metadata=metadata or {}
        )
        self._tasks[task.id] = task
        logger.info(f"Added scheduled task: {name} ({task_type}) with schedule: {schedule}")
        return task

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"Removed scheduled task: {task_id}")
            return True
        return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[ScheduledTask]:
        """List all tasks."""
        return list(self._tasks.values())

    def enable_task(self, task_id: str) -> bool:
        """Enable a task."""
        task = self._tasks.get(task_id)
        if task:
            task.enabled = True
            logger.info(f"Enabled task: {task.name}")
            return True
        return False

    def disable_task(self, task_id: str) -> bool:
        """Disable a task."""
        task = self._tasks.get(task_id)
        if task:
            task.enabled = False
            logger.info(f"Disabled task: {task.name}")
            return True
        return False

    def should_run(self, task: ScheduledTask) -> bool:
        """Check if a task should run based on its schedule.
        
        This is a simplified check. In production, use a proper cron parser.
        For now, we'll just check if the task is enabled and hasn't run recently.
        """
        if not task.enabled:
            return False
        
        # Simple check: if no last run, run it
        if task.last_run is None:
            return True
        
        # For production, parse the cron expression and check if current time matches
        # For now, we'll just use a simple interval based on the schedule string
        # This is a placeholder for proper cron parsing
        from datetime import timedelta
        
        # Parse simple interval formats like "5m", "1h", "1d"
        schedule_lower = task.schedule.lower()
        if schedule_lower.endswith('m'):
            minutes = int(schedule_lower[:-1])
            return datetime.utcnow() - task.last_run >= timedelta(minutes=minutes)
        elif schedule_lower.endswith('h'):
            hours = int(schedule_lower[:-1])
            return datetime.utcnow() - task.last_run >= timedelta(hours=hours)
        elif schedule_lower.endswith('d'):
            days = int(schedule_lower[:-1])
            return datetime.utcnow() - task.last_run >= timedelta(days=days)
        
        # Default: don't run
        return False

    async def run_due_tasks(self, task_runner: Callable) -> list[ScheduledTask]:
        """Run all tasks that are due."""
        run_tasks = []
        for task in self._tasks.values():
            if self.should_run(task):
                logger.info(f"Running scheduled task: {task.name}")
                try:
                    await task_runner(task)
                    task.last_run = datetime.utcnow()
                    task.run_count += 1
                    run_tasks.append(task)
                except Exception as e:
                    logger.error(f"Task {task.name} failed: {e}")
        
        return run_tasks


# Global scheduler instance
_global_scheduler: Optional[SimpleScheduler] = None


def get_scheduler() -> SimpleScheduler:
    """Get the global scheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = SimpleScheduler()
        # Add default research tasks
        _global_scheduler.add_task(
            name="Daily Gap Analysis",
            task_type="analyze_gaps",
            schedule="1d",
            metadata={"description": "Analyze research gaps daily"}
        )
        _global_scheduler.add_task(
            name="Weekly Hypothesis Generation",
            task_type="generate_hypotheses",
            schedule="7d",
            metadata={"description": "Generate new hypotheses weekly"}
        )
        _global_scheduler.add_task(
            name="Daily Synthesis",
            task_type="synthesis",
            schedule="1d",
            metadata={"description": "Synthesize information across sources daily"}
        )
    return _global_scheduler
