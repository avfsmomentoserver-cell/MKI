"""Documentation storage with version tracking."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from mkc.core.database import Base

logger = logging.getLogger("mkc.models.documentation")


class GeneratedDocument(Base):
    """A generated document with version tracking."""
    __tablename__ = "generated_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False, index=True)  # overview, api_reference, etc.
    content = Column(Text, nullable=False)
    source_ko_ids = Column(JSONB, nullable=False, default=list)  # List of KO IDs used
    version = Column(Integer, nullable=False, default=1)
    author = Column(String(100), nullable=False, default="ai")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    previous_version_id = Column(UUID(as_uuid=True), ForeignKey("generated_documents.id"), nullable=True)
    previous_version = relationship("GeneratedDocument", remote_side=[id], backref="next_versions")
    
    # Indexes
    __table_args__ = (
        Index("idx_generated_documents_type_version", "doc_type", "version"),
        Index("idx_generated_documents_created_at", "created_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "title": self.title,
            "doc_type": self.doc_type,
            "content": self.content,
            "source_ko_ids": self.source_ko_ids,
            "version": self.version,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "previous_version_id": str(self.previous_version_id) if self.previous_version_id else None,
        }

    @classmethod
    def select(cls):
        """Compatibility method for analysis code."""
        return cls.__table__.select()


class DocumentUpdateTrigger(Base):
    """Tracks when documents should be regenerated based on knowledge changes."""
    __tablename__ = "document_update_triggers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("generated_documents.id"), nullable=False)
    trigger_reason = Column(String(500), nullable=False)  # e.g., "new_ko_added", "ko_updated"
    source_ko_id = Column(UUID(as_uuid=True), nullable=True)  # The KO that triggered the update
    triggered_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    processed = Column(Integer, nullable=False, default=0)  # 0 = pending, 1 = processing, 2 = completed
    
    # Relationships
    document = relationship("GeneratedDocument", backref="update_triggers")
    
    # Indexes
    __table_args__ = (
        Index("idx_document_update_triggers_processed", "processed"),
        Index("idx_document_update_triggers_document_id", "document_id"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "trigger_reason": self.trigger_reason,
            "source_ko_id": str(self.source_ko_id) if self.source_ko_id else None,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "processed": self.processed,
        }

    @classmethod
    def select(cls):
        """Compatibility method for analysis code."""
        return cls.__table__.select()
