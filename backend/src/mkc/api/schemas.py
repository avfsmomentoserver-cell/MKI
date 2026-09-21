"""Pydantic request/response schemas for the MKC API.

Schemas are the public contract: every field a client may send is declared
here with validation; responses are produced by the models' ``to_dict()``
helpers, so nothing internal (ORM instances, engine internals) ever leaks.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from mkc.core.constants import (
    DECISION_STATUSES,
    EXPERIMENT_STATUSES,
    KNOWLEDGE_STATUSES,
    KNOWLEDGE_TYPES,
    LIFECYCLE_STATES,
    RESEARCH_STATUSES,
)

MAX_PAGE_SIZE = 200


class Pagination(BaseModel):
    """Cursor-free page window applied to list endpoints."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=MAX_PAGE_SIZE)


class PagedResponse(BaseModel):
    """Envelope for paginated list endpoints."""

    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class KnowledgeIn(BaseModel):
    """Body for POST /api/v1/knowledge.

    ``provenance`` must carry at least ``source_location`` — the registry
    refuses objects without a location, because unlocated claims cannot be
    audited (provenance is not optional in MKC).
    """

    type: str = Field(description="knowledge object type (e.g. hypothesis, decision)")
    title: str = Field(min_length=1, max_length=1024)
    content_summary: str = Field(default="")
    body: str = Field(default="")
    lifecycle_state: str = Field(default="unknown")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_id: str | None = Field(default=None, description="UUID of a registered source")
    provenance: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active")

    def validate_against_registry(self) -> None:
        """Raise ValueError on any enum violation; called by the router."""
        if self.type not in KNOWLEDGE_TYPES:
            raise ValueError(f"type must be one of: {', '.join(sorted(KNOWLEDGE_TYPES))}")
        if self.lifecycle_state not in LIFECYCLE_STATES:
            raise ValueError(f"lifecycle_state must be one of: {', '.join(sorted(LIFECYCLE_STATES))}")
        if self.status not in KNOWLEDGE_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(KNOWLEDGE_STATUSES))}")
        if not self.provenance.get("source_location"):
            raise ValueError("provenance.source_location is required (unlocated claims cannot be audited)")


class KnowledgePatch(BaseModel):
    """Body for PATCH /api/v1/knowledge/{id}.

    Only mutable fields are accepted. ``provenance`` is deliberately absent:
    provenance is immutable in MKC. ``lifecycle_state`` changes are validated
    against the lifecycle state machine using the ``actor`` field.
    """

    title: str | None = Field(default=None, min_length=1, max_length=1024)
    content_summary: str | None = None
    body: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    lifecycle_state: str | None = None
    status: str | None = None
    actor: str = Field(default="api", description="who is making this change (audited)")


class ResearchItemIn(BaseModel):
    """Body for POST /api/v1/research."""

    knowledge_id: str = Field(description="UUID of the parent knowledge object")
    title: str = Field(min_length=1, max_length=1024)
    topic: str = Field(default="")
    status: str = Field(default="planned")
    hypothesis: str = Field(default="")
    evidence_count: int = Field(default=0, ge=0)
    validation_level: str = Field(default="")
    related_modules: list[str] = Field(default_factory=list)

    def validate_against_registry(self) -> None:
        """Raise ValueError on any enum violation; called by the router."""
        if self.status not in RESEARCH_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(RESEARCH_STATUSES))}")


class ResearchItemPatch(BaseModel):
    """Body for PATCH /api/v1/research/{id} (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=1024)
    topic: str | None = None
    status: str | None = None
    hypothesis: str | None = None
    evidence_count: int | None = Field(default=None, ge=0)
    validation_level: str | None = None
    related_modules: list[str] | None = None
    actor: str = Field(default="api")


class DecisionIn(BaseModel):
    """Body for POST /api/v1/decisions."""

    knowledge_id: str = Field(description="UUID of the parent knowledge object")
    title: str = Field(min_length=1, max_length=1024)
    context: str = Field(default="")
    problem: str = Field(default="")
    alternatives: str = Field(default="")
    decision_text: str = Field(min_length=1)
    reason: str = Field(default="")
    evidence: str = Field(default="")
    affected_components: list[str] = Field(default_factory=list)
    status: str = Field(default="proposed")
    author: str = Field(default="")
    decided_at: date | None = None

    def validate_against_registry(self) -> None:
        """Raise ValueError on any enum violation; called by the router."""
        if self.status not in DECISION_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(DECISION_STATUSES))}")


class DecisionPatch(BaseModel):
    """Body for PATCH /api/v1/decisions/{id} (all fields optional)."""

    context: str | None = None
    problem: str | None = None
    alternatives: str | None = None
    decision_text: str | None = None
    reason: str | None = None
    evidence: str | None = None
    affected_components: list[str] | None = None
    status: str | None = None
    author: str | None = None
    decided_at: date | None = None
    actor: str = Field(default="api")


class SupersedeIn(BaseModel):
    """Body for POST /api/v1/decisions/{id}/supersede."""

    superseded_by: str | None = Field(default=None, description="decision id or title replacing this one")
    reason: str = Field(min_length=1)
    actor: str = Field(default="api")


class ExperimentIn(BaseModel):
    """Body for POST /api/v1/experiments."""

    knowledge_id: str = Field(description="UUID of the parent knowledge object")
    title: str = Field(min_length=1, max_length=1024)
    hypothesis_tested: str = Field(default="")
    dataset: str = Field(default="")
    method: str = Field(default="")
    result: str = Field(default="")
    statistics_json: dict[str, Any] = Field(default_factory=dict)
    conclusion: str = Field(default="")
    status: str = Field(default="planned")
    reproducibility: str = Field(default="")
    limitations: str = Field(default="")

    def validate_against_registry(self) -> None:
        """Raise ValueError on any enum violation; called by the router."""
        if self.status not in EXPERIMENT_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(EXPERIMENT_STATUSES))}")


class ExperimentPatch(BaseModel):
    """Body for PATCH /api/v1/experiments/{id} (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=1024)
    hypothesis_tested: str | None = None
    dataset: str | None = None
    method: str | None = None
    result: str | None = None
    statistics_json: dict[str, Any] | None = None
    conclusion: str | None = None
    status: str | None = None
    reproducibility: str | None = None
    limitations: str | None = None
    actor: str = Field(default="api")


class ValidateExperimentIn(BaseModel):
    """Body for POST /api/v1/experiments/{id}/validate."""

    actor: str = Field(description="the human performing validation (must not be 'auto')")
    notes: str = Field(default="")


def knowledge_error_payload(code: str, detail: str, **extra: Any) -> dict[str, Any]:
    """Standard error body: {error: {code, detail, ...extra}}."""
    payload: dict[str, Any] = {"code": code, "detail": detail}
    payload.update(extra)
    return {"error": payload}
