"""Library analytics and metrics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import func

from mkc.models import KnowledgeObject, Document, Source, GeneratedDocument, GeneratedBook, Insight, Contradiction

logger = logging.getLogger("mkc.intelligence.library")


@dataclass
class LibraryMetrics:
    """Overall library metrics."""
    total_knowledge_objects: int = 0
    total_documents: int = 0
    total_sources: int = 0
    total_generated_documents: int = 0
    total_generated_books: int = 0
    total_insights: int = 0
    total_contradictions: int = 0
    
    # Type distributions
    ko_type_distribution: dict[str, int] = field(default_factory=dict)
    document_type_distribution: dict[str, int] = field(default_factory=dict)
    
    # Lifecycle state distribution
    lifecycle_distribution: dict[str, int] = field(default_factory=dict)
    
    # Activity metrics
    knowledge_objects_last_7_days: int = 0
    knowledge_objects_last_30_days: int = 0
    
    # Quality metrics
    average_confidence: float = 0.0
    high_confidence_count: int = 0  # confidence > 0.8
    low_confidence_count: int = 0   # confidence < 0.5
    
    # Generated content metrics
    avg_doc_chapters: float = 0.0
    avg_book_chapters: float = 0.0
    
    metadata: dict[str, Any] = field(default_factory=dict)


class LibraryAnalytics:
    """Analyze library usage and metrics."""

    def __init__(self):
        pass

    def compute_metrics(self, session: Session) -> LibraryMetrics:
        """Compute comprehensive library metrics."""
        logger.info("Computing library metrics")
        
        metrics = LibraryMetrics()
        
        # Basic counts
        metrics.total_knowledge_objects = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active"
        ).count()
        
        metrics.total_documents = session.query(Document).count()
        metrics.total_sources = session.query(Source).count()
        metrics.total_generated_documents = session.query(GeneratedDocument).count()
        metrics.total_generated_books = session.query(GeneratedBook).count()
        metrics.total_insights = session.query(Insight).count()
        metrics.total_contradictions = session.query(Contradiction).count()
        
        # Type distributions
        ko_types = session.query(
            KnowledgeObject.type,
            func.count(KnowledgeObject.id)
        ).filter(KnowledgeObject.status == "active").group_by(KnowledgeObject.type).all()
        
        for ko_type, count in ko_types:
            metrics.ko_type_distribution[ko_type] = count
        
        doc_types = session.query(
            Document.doc_type,
            func.count(Document.id)
        ).group_by(Document.doc_type).all()
        
        for doc_type, count in doc_types:
            metrics.document_type_distribution[doc_type] = count
        
        # Lifecycle distribution
        lifecycle_states = session.query(
            KnowledgeObject.lifecycle_state,
            func.count(KnowledgeObject.id)
        ).filter(KnowledgeObject.status == "active").group_by(KnowledgeObject.lifecycle_state).all()
        
        for state, count in lifecycle_states:
            metrics.lifecycle_distribution[state] = count
        
        # Activity metrics
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        metrics.knowledge_objects_last_7_days = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active",
            KnowledgeObject.created_at >= seven_days_ago
        ).count()
        
        metrics.knowledge_objects_last_30_days = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active",
            KnowledgeObject.created_at >= thirty_days_ago
        ).count()
        
        # Quality metrics
        avg_conf = session.query(func.avg(KnowledgeObject.confidence)).filter(
            KnowledgeObject.status == "active"
        ).scalar()
        
        metrics.average_confidence = float(avg_conf) if avg_conf else 0.0
        
        metrics.high_confidence_count = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active",
            KnowledgeObject.confidence > 0.8
        ).count()
        
        metrics.low_confidence_count = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active",
            KnowledgeObject.confidence < 0.5
        ).count()
        
        # Generated content metrics
        avg_doc_chapters = session.query(func.avg(GeneratedDocument.chapter_count)).scalar()
        metrics.avg_doc_chapters = float(avg_doc_chapters) if avg_doc_chapters else 0.0
        
        avg_book_chapters = session.query(func.avg(GeneratedBook.chapter_count)).scalar()
        metrics.avg_book_chapters = float(avg_book_chapters) if avg_book_chapters else 0.0
        
        # Timestamp
        metrics.metadata["computed_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Computed metrics: {metrics.total_knowledge_objects} KOs, {metrics.total_documents} docs")
        
        return metrics

    def get_growth_trends(self, session: Session, days: int = 30) -> dict[str, Any]:
        """Get growth trends over time."""
        logger.info(f"Computing growth trends for {days} days")
        
        trends = {}
        
        # Daily KO creation for the last N days
        for i in range(days):
            date = datetime.utcnow() - timedelta(days=i)
            date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            count = session.query(KnowledgeObject).filter(
                KnowledgeObject.created_at >= date_start,
                KnowledgeObject.created_at <= date_end
            ).count()
            
            trends[date.date().isoformat()] = count
        
        return {
            "period_days": days,
            "daily_ko_creation": trends,
        }

    def get_top_sources(self, session: Session, limit: int = 10) -> list[dict[str, Any]]:
        """Get top sources by knowledge object count."""
        from sqlalchemy import desc
        
        # Count KOs per source
        source_counts = session.query(
            KnowledgeObject.source_id,
            func.count(KnowledgeObject.id)
        ).filter(KnowledgeObject.status == "active").group_by(KnowledgeObject.source_id).order_by(
            desc(func.count(KnowledgeObject.id))
        ).limit(limit).all()
        
        results = []
        for source_id, count in source_counts:
            source = session.query(Source).filter(Source.id == source_id).first()
            if source:
                results.append({
                    "source_id": str(source.id),
                    "source_type": source.source_type,
                    "source_id_str": source.source_id,
                    "ko_count": count,
                    "indexed_at": source.indexed_at.isoformat() if source.indexed_at else None,
                })
        
        return results
