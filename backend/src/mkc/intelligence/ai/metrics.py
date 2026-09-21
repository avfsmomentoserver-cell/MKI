"""AI usage tracking and metrics.

Tracks token usage, costs, and success/failure rates for AI providers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("mkc.ai.metrics")


@dataclass
class UsageRecord:
    """A single AI usage record."""
    id: str = field(default_factory=lambda: str(uuid4()))
    provider: str = ""
    model: str = ""
    task_type: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    error: Optional[str] = None


class UsageTracker:
    """Track AI usage metrics."""

    def __init__(self):
        self._records: list[UsageRecord] = []
        self._current_session_usage: dict[str, UsageRecord] = {}

    def record_usage(self, provider: str, model: str, task_type: str,
                     prompt_tokens: int, completion_tokens: int,
                     cost_estimate_usd: float, success: bool = True,
                     error: Optional[str] = None) -> None:
        """Record a usage event."""
        record = UsageRecord(
            provider=provider,
            model=model,
            task_type=task_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_estimate_usd=cost_estimate_usd,
            success=success,
            error=error
        )
        self._records.append(record)
        logger.info(f"Usage recorded: {provider}/{model} - {total_tokens} tokens, ${cost_estimate_usd:.4f}")

    def get_total_usage(self, provider: Optional[str] = None) -> dict[str, int]:
        """Get total usage metrics."""
        records = self._records
        if provider:
            records = [r for r in records if r.provider == provider]
        
        return {
            "total_tokens": sum(r.total_tokens for r in records),
            "prompt_tokens": sum(r.prompt_tokens for r in records),
            "completion_tokens": sum(r.completion_tokens for r in records),
            "total_cost_usd": sum(r.cost_estimate_usd for r in records),
            "total_calls": len(records),
            "successful_calls": sum(1 for r in records if r.success),
            "failed_calls": sum(1 for r in records if not r.success),
        }

    def get_usage_by_task_type(self, task_type: str) -> dict[str, int]:
        """Get usage metrics for a specific task type."""
        records = [r for r in self._records if r.task_type == task_type]
        return {
            "total_tokens": sum(r.total_tokens for r in records),
            "total_cost_usd": sum(r.cost_estimate_usd for r in records),
            "total_calls": len(records),
            "successful_calls": sum(1 for r in records if r.success),
        }

    def get_recent_records(self, limit: int = 100) -> list[UsageRecord]:
        """Get recent usage records."""
        return self._records[-limit:]


# Global usage tracker instance
_global_tracker: Optional[UsageTracker] = None


def get_tracker() -> UsageTracker:
    """Get the global usage tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = UsageTracker()
    return _global_tracker
