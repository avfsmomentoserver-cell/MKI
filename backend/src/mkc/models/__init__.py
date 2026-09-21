"""Declarative model definitions for every MKC table.

All models are SQLAlchemy 2.0 typed (``Mapped``/``mapped_column``) and
register their tables on ``mkc.core.database.Base.metadata`` — Alembic
autogeneration and ``Base.metadata.create_all`` both rely on importing this
module first.

Conventions:

- snake_case ``__tablename__`` for every table.
- UUIDv4 primary keys (``id``).
- ``to_dict()`` on every model returns a JSON-safe dict (UUIDs and datetimes
  serialized to ISO-8601 strings) so routers never leak ORM instances.
- Provenance is data, not metadata: ``KnowledgeObject.provenance`` (JSONB)
  carries original_text / extraction_method / source_type / source_location /
  author and is immutable by API policy (never updated by PATCH).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mkc.core.database import Base

__all__ = [
    "AuditLog",
    "Contradiction",
    "Decision",
    "Document",
    "Entity",
    "EntityRelation",
    "Experiment",
    "Insight",
    "KnowledgeObject",
    "Report",
    "ResearchItem",
    "Source",
    "new_uuid",
    "utcnow",
]


def new_uuid() -> uuid.UUID:
    """Default primary-key factory: random UUIDv4."""
    return uuid.uuid4()


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp used for all *at columns."""
    return datetime.now(UTC)


class Source(Base):
    """A registered ingestion source (git repo, markdown bundle, chatgpt archive...)."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(512), index=True)
    path: Mapped[str] = mapped_column(String(1024), default="")
    metadata_json: Mapped[dict] = mapped_column("metadata_json", JSONB, default=dict)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict (UUIDs/datetimes -> strings)."""
        return {
            "id": str(self.id),
            "source_type": self.source_type,
            "source_id": self.source_id,
            "path": self.path,
            "metadata_json": self.metadata_json or {},
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
        }


class Document(Base):
    """A file ingested from a source, classified by doc_type."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), index=True)
    file_hash: Mapped[str] = mapped_column(String(128), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    doc_type: Mapped[str] = mapped_column(String(32), default="other", index=True)
    title: Mapped[str] = mapped_column(String(1024), default="")
    section_tree: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict (UUIDs/datetimes -> strings)."""
        return {
            "id": str(self.id),
            "source_id": str(self.source_id),
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "size_bytes": self.size_bytes,
            "doc_type": self.doc_type,
            "title": self.title,
            "section_tree": self.section_tree or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeObject(Base):
    """A structured knowledge object with immutable provenance.

    Provenance contract (never fabricated):

    - ``original_text``: verbatim excerpt of the material the object was
      extracted from.
    - ``extraction_method``: which pipeline produced the object
      (``manual`` / ``heuristic`` / ``llm:<model>``).
    - ``source_type``: one of ``SOURCE_TYPES`` (git, markdown, chatgpt, ...).
    - ``source_location``: where in the source (repo path, line range,
      message id, commit hash...).
    - ``author``: who/what is responsible for the assertion.

    ``lifecycle_state`` is the epistemic status; the state machine in
    :mod:`mkc.core.lifecycle` decides which transitions are legal and which
    require a human actor. The API treats ``provenance`` as immutable:
    PATCH never accepts changes to it.
    """

    __tablename__ = "knowledge_objects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(1024), index=True)
    content_summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    lifecycle_state: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True, nullable=True
    )
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict (UUIDs/datetimes -> strings)."""
        return {
            "id": str(self.id),
            "type": self.type,
            "title": self.title,
            "content_summary": self.content_summary,
            "body": self.body,
            "lifecycle_state": self.lifecycle_state,
            "confidence": self.confidence,
            "source_id": str(self.source_id) if self.source_id else None,
            "provenance": self.provenance or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Entity(Base):
    """A named, kinded thing in the knowledge graph (module, engine, person...)."""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("name", "kind", name="uq_entities_name_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(512), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    attributes_json: Mapped[dict] = mapped_column("attributes_json", JSONB, default=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "name": self.name,
            "kind": self.kind,
            "attributes_json": self.attributes_json or {},
        }


class EntityRelation(Base):
    """A typed, confidence-scored edge between two documents/knowledge objects."""

    __tablename__ = "entity_relations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    from_id: Mapped[str] = mapped_column(String(64), index=True)
    to_id: Mapped[str] = mapped_column(String(64), index=True)
    rel_type: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    reason: Mapped[str] = mapped_column(Text, default="")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "from_id": self.from_id,
            "to_id": self.to_id,
            "rel_type": self.rel_type,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class ResearchItem(Base):
    """A tracked research thread attached to a knowledge object."""

    __tablename__ = "research_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(1024), index=True)
    topic: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_level: Mapped[str] = mapped_column(String(64), default="")
    related_modules: Mapped[list] = mapped_column(JSONB, default=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "knowledge_id": str(self.knowledge_id),
            "title": self.title,
            "topic": self.topic,
            "status": self.status,
            "hypothesis": self.hypothesis,
            "evidence_count": self.evidence_count,
            "validation_level": self.validation_level,
            "related_modules": self.related_modules or [],
        }


class Decision(Base):
    """A recorded decision (kept, never overwritten; superseded via status)."""

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(1024), index=True)
    context: Mapped[str] = mapped_column(Text, default="")
    problem: Mapped[str] = mapped_column(Text, default="")
    alternatives: Mapped[str] = mapped_column(Text, default="")
    decision_text: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    affected_components: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    author: Mapped[str] = mapped_column(String(512), default="")
    decided_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "knowledge_id": str(self.knowledge_id),
            "title": self.title,
            "context": self.context,
            "problem": self.problem,
            "alternatives": self.alternatives,
            "decision_text": self.decision_text,
            "reason": self.reason,
            "evidence": self.evidence,
            "affected_components": self.affected_components or [],
            "status": self.status,
            "author": self.author,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }


class Experiment(Base):
    """A runnable experiment attached to a knowledge object; failed runs stay in the record."""

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(1024), index=True)
    hypothesis_tested: Mapped[str] = mapped_column(Text, default="")
    dataset: Mapped[str] = mapped_column(String(1024), default="")
    method: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    statistics_json: Mapped[dict] = mapped_column("statistics_json", JSONB, default=dict)
    conclusion: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    reproducibility: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "knowledge_id": str(self.knowledge_id),
            "title": self.title,
            "hypothesis_tested": self.hypothesis_tested,
            "dataset": self.dataset,
            "method": self.method,
            "result": self.result,
            "statistics_json": self.statistics_json or {},
            "conclusion": self.conclusion,
            "status": self.status,
            "reproducibility": self.reproducibility,
            "limitations": self.limitations,
        }


class Insight(Base):
    """A cross-object observation (pattern/trend/gap/contradiction/recommendation)."""

    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    knowledge_ids: Mapped[list] = mapped_column(JSONB, default=list)
    insight_type: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    supporting_evidence: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "knowledge_ids": self.knowledge_ids or [],
            "insight_type": self.insight_type,
            "summary": self.summary,
            "supporting_evidence": self.supporting_evidence or [],
            "confidence": self.confidence,
            "status": self.status,
        }


class Contradiction(Base):
    """A flagged conflict between two claims; kept until explicitly resolved."""

    __tablename__ = "contradictions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    claim_a_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_b_id: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="flagged", index=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[str] = mapped_column(String(512), default="")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "claim_a_id": self.claim_a_id,
            "claim_b_id": self.claim_b_id,
            "severity": self.severity,
            "status": self.status,
            "explanation": self.explanation,
            "resolved_by": self.resolved_by,
        }


class AuditLog(Base):
    """Append-only audit trail: lifecycle transitions, API mutations, ingestion."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    action: Mapped[str] = mapped_column(String(128), index=True)
    actor: Mapped[str] = mapped_column(String(512), default="")
    object_type: Mapped[str] = mapped_column(String(64), index=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "action": self.action,
            "actor": self.actor,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "details": self.details or {},
            "at": self.at.isoformat() if self.at else None,
        }


class Report(Base):
    """A generated MKC report (project-knowledge, research-gaps, ...)."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(String(1024), default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    summary: Mapped[str] = mapped_column(Text, default="")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": str(self.id),
            "type": self.type,
            "path": self.path,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "summary": self.summary,
        }
