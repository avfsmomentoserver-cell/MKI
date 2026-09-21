"""Database models for scheduled research tasks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from mkc.core.database import Base

logger = logging.getLogger("mkc.models.research")


class ScheduledResearchTask(Base):
    """A scheduled research task definition."""
    __tablename__ = "scheduled_research_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(500), nullable=False, index=True)
    task_type = Column(String(100), nullable=False, index=True)  # analyze_gaps, generate_hypotheses, etc.
    schedule = Column(String(100), nullable=False)  # cron expression or interval
    enabled = Column(Integer, nullable=False, default=1)  # 0 = disabled, 1 = enabled
    last_run = Column(DateTime(timezone=True), nullable=True)
    next_run = Column(DateTime(timezone=True), nullable=True)
    run_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_scheduled_research_tasks_enabled", "enabled"),
        Index("idx_scheduled_research_tasks_next_run", "next_run"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "task_type": self.task_type,
            "schedule": self.schedule,
            "enabled": bool(self.enabled),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def select(cls):
        """Compatibility method for analysis code."""
        return cls.__table__.select()


class ResearchTaskExecution(Base):
    """A record of a research task execution."""
    __tablename__ = "research_task_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("scheduled_research_tasks.id"), nullable=False)
    task_type = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, index=True)  # running, completed, failed
    findings = Column(JSONB, nullable=False, default=list)
    insights_generated = Column(Integer, nullable=False, default=0)
    contradictions_found = Column(Integer, nullable=False, default=0)
    hypotheses_generated = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    task = relationship("ScheduledResearchTask", backref="executions")
    
    # Indexes
    __table_args__ = (
        Index("idx_research_task_executions_status", "status"),
        Index("idx_research_task_executions_task_id", "task_id"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "task_type": self.task_type,
            "status": self.status,
            "findings": self.findings or [],
            "insights_generated": self.insights_generated,
            "contradictions_found": self.contradictions_found,
            "hypotheses_generated": self.hypotheses_generated,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def select(cls):
        """Compatibility method for analysis code."""
        return cls.__table__.select()
