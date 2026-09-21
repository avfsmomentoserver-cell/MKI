"""Database models for generated books."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from mkc.core.database import Base

logger = logging.getLogger("mkc.models.books")


class GeneratedBook(Base):
    """A generated book from knowledge objects."""
    __tablename__ = "generated_books"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=False, index=True)
    subtitle = Column(String(500), nullable=True)
    author = Column(String(200), nullable=False, default="MKC System")
    description = Column(Text, nullable=True)
    structure_type = Column(String(50), nullable=False, default="topic_based")  # topic_based, chronological, type_based
    content_markdown = Column(Text, nullable=False)
    content_html = Column(Text, nullable=True)
    table_of_contents = Column(Text, nullable=True)
    source_ko_ids = Column(JSONB, nullable=False, default=list)
    chapter_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_generated_books_structure_type", "structure_type"),
        Index("idx_generated_books_created_at", "created_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "description": self.description,
            "structure_type": self.structure_type,
            "content_markdown": self.content_markdown,
            "content_html": self.content_html,
            "table_of_contents": self.table_of_contents,
            "source_ko_ids": self.source_ko_ids or [],
            "chapter_count": self.chapter_count,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def select(cls):
        """Compatibility method for analysis code."""
        return cls.__table__.select()


class BookChapter(Base):
    """A chapter within a generated book."""
    __tablename__ = "book_chapters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    book_id = Column(UUID(as_uuid=True), ForeignKey("generated_books.id"), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    order = Column(Integer, nullable=False)
    source_ko_ids = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Relationships
    book = relationship("GeneratedBook", backref="chapters")
    
    # Indexes
    __table_args__ = (
        Index("idx_book_chapters_book_id", "book_id"),
        Index("idx_book_chapters_order", "order"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "book_id": str(self.book_id),
            "title": self.title,
            "content": self.content,
            "order": self.order,
            "source_ko_ids": self.source_ko_ids or [],
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def select(cls):
        """Compatibility method for analysis code."""
        return cls.__table__.select()
