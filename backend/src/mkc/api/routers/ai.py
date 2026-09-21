"""API router for AI-related endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mkc.core.auth import require_token
from mkc.core.database import get_session
from mkc.intelligence.ai.metrics import get_tracker
from mkc.intelligence.ai.queue import get_queue
from mkc.intelligence.ai.providers import get_provider

logger = logging.getLogger("mkc.api.ai")

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/usage")
async def get_usage_metrics(provider: str = None, session: Session = Depends(get_session)):
    """Get AI usage metrics."""
    tracker = get_tracker()
    if provider:
        metrics = tracker.get_total_usage(provider)
    else:
        metrics = tracker.get_total_usage()
    return metrics


@router.get("/usage/by-task/{task_type}")
async def get_usage_by_task(task_type: str, session: Session = Depends(get_session)):
    """Get usage metrics for a specific task type."""
    tracker = get_tracker()
    metrics = tracker.get_usage_by_task_type(task_type)
    return metrics


@router.get("/queue/status")
async def get_queue_status(session: Session = Depends(get_session)):
    """Get task queue status."""
    queue = get_queue()
    return queue.get_queue_status()


@router.post("/test-provider")
async def test_provider(provider_type: str = "entrim", 
                       prompt: str = "Test prompt",
                       session: Session = Depends(get_session)):
    """Test AI provider connection."""
    try:
        provider = get_provider(provider_type)
        response = await provider.generate(prompt)
        return {
            "success": True,
            "provider": provider_type,
            "model": provider.model,
            "content_preview": response.content[:200],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "cost_estimate_usd": response.usage.cost_estimate_usd,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enqueue")
async def enqueue_task(task_type: str, payload: dict[str, Any],
                     priority: str = "normal",
                     session: Session = Depends(get_session)):
    """Enqueue an AI task."""
    from mkc.intelligence.ai.queue import TaskPriority
    
    priority_map = {
        "low": TaskPriority.LOW,
        "normal": TaskPriority.NORMAL,
        "high": TaskPriority.HIGH,
        "urgent": TaskPriority.URGENT,
    }
    
    task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
    queue = get_queue()
    task = await queue.enqueue(task_type, payload, priority=task_priority)
    
    return {
        "task_id": task.id,
        "task_type": task_type,
        "priority": priority,
        "status": task.status.value,
    }


@router.get("/task/{task_id}")
async def get_task_status(task_id: str, session: Session = Depends(get_session)):
    """Get task status."""
    queue = get_queue()
    task = queue.get_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status.value,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "result": task.result,
        "error": task.error,
        "retry_count": task.retry_count,
    }
