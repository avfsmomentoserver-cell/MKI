"""API router for scheduled research tasks."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mkc.core.auth import require_token
from mkc.core.database import get_session
from mkc.intelligence.research.runner import ResearchTaskRunner, ResearchTaskType
from mkc.models import ScheduledResearchTask, ResearchTaskExecution

logger = logging.getLogger("mkc.api.research")

router = APIRouter(prefix="/research-tasks", tags=["research-tasks"])


@router.get("/scheduled")
async def list_scheduled_tasks(enabled_only: bool = False, session: Session = Depends(get_session)):
    """List scheduled research tasks."""
    query = session.query(ScheduledResearchTask)
    
    if enabled_only:
        query = query.filter(ScheduledResearchTask.enabled == 1)
    
    tasks = query.order_by(ScheduledResearchTask.created_at.desc()).all()
    return [task.to_dict() for task in tasks]


@router.get("/scheduled/{task_id}")
async def get_scheduled_task(task_id: str, session: Session = Depends(get_session)):
    """Get a specific scheduled task."""
    task = session.query(ScheduledResearchTask).filter(
        ScheduledResearchTask.id == task_id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task.to_dict()


@router.post("/scheduled")
async def create_scheduled_task(name: str, task_type: str, schedule: str, 
                               metadata: dict[str, Any] = None,
                               session: Session = Depends(get_session)):
    """Create a new scheduled research task."""
    task = ScheduledResearchTask(
        name=name,
        task_type=task_type,
        schedule=schedule,
        enabled=1,
        metadata_json=metadata or {}
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    
    logger.info(f"Created scheduled task: {task.id} ({name})")
    return task.to_dict()


@router.put("/scheduled/{task_id}")
async def update_scheduled_task(task_id: str, 
                               enabled: Optional[bool] = None,
                               schedule: Optional[str] = None,
                               session: Session = Depends(get_session)):
    """Update a scheduled task."""
    task = session.query(ScheduledResearchTask).filter(
        ScheduledResearchTask.id == task_id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if enabled is not None:
        task.enabled = 1 if enabled else 0
    if schedule is not None:
        task.schedule = schedule
    
    session.commit()
    session.refresh(task)
    
    return task.to_dict()


@router.delete("/scheduled/{task_id}")
async def delete_scheduled_task(task_id: str, session: Session = Depends(get_session)):
    """Delete a scheduled task."""
    task = session.query(ScheduledResearchTask).filter(
        ScheduledResearchTask.id == task_id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    session.delete(task)
    session.commit()
    
    return {"status": "deleted", "task_id": task_id}


@router.get("/scheduled/{task_id}/executions")
async def get_task_executions(task_id: str, limit: int = 20, session: Session = Depends(get_session)):
    """Get execution history for a scheduled task."""
    executions = session.query(ResearchTaskExecution).filter(
        ResearchTaskExecution.task_id == task_id
    ).order_by(ResearchTaskExecution.started_at.desc()).limit(limit).all()
    
    return [exec.to_dict() for exec in executions]


@router.post("/run")
async def run_research_task(task_type: str, session: Session = Depends(get_session)):
    """Run a research task immediately (not scheduled)."""
    task_type_map = {
        "analyze_gaps": ResearchTaskType.ANALYZE_GAPS,
        "generate_hypotheses": ResearchTaskType.GENERATE_HYPOTHESES,
        "synthesis": ResearchTaskType.SYNTHESIS,
        "contradiction_deep_dive": ResearchTaskType.CONTRADICTION_DEEP_DIVE,
        "cross_source_analysis": ResearchTaskType.CROSS_SOURCE_ANALYSIS,
    }
    
    if task_type not in task_type_map:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")
    
    try:
        runner = ResearchTaskRunner()
        result = await runner.run_task(task_type_map[task_type], session)
        
        # Record execution
        execution = ResearchTaskExecution(
            task_id=None,  # Not a scheduled task
            task_type=task_type,
            status=result.status,
            findings=result.findings,
            insights_generated=result.insights_generated,
            contradictions_found=result.contradictions_found,
            hypotheses_generated=result.hypotheses_generated,
            error_message=result.error,
            started_at=result.started_at,
            completed_at=result.completed_at
        )
        session.add(execution)
        session.commit()
        session.refresh(execution)
        
        return execution.to_dict()
        
    except Exception as e:
        logger.error(f"Research task failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions")
async def list_executions(task_type: Optional[str] = None, 
                         status: Optional[str] = None,
                         limit: int = 50,
                         session: Session = Depends(get_session)):
    """List research task executions."""
    query = session.query(ResearchTaskExecution)
    
    if task_type:
        query = query.filter(ResearchTaskExecution.task_type == task_type)
    if status:
        query = query.filter(ResearchTaskExecution.status == status)
    
    executions = query.order_by(ResearchTaskExecution.started_at.desc()).limit(limit).all()
    return [exec.to_dict() for exec in executions]


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, session: Session = Depends(get_session)):
    """Get a specific execution."""
    execution = session.query(ResearchTaskExecution).filter(
        ResearchTaskExecution.id == execution_id
    ).first()
    
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return execution.to_dict()
