"""Research item CRUD (tracked research threads attached to knowledge objects)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mkc.api.metrics import metrics
from mkc.api.schemas import PagedResponse, ResearchItemIn, ResearchItemPatch, knowledge_error_payload
from mkc.core.audit import audit
from mkc.core.auth import AuthToken
from mkc.core.constants import RESEARCH_STATUSES
from mkc.core.database import get_session
from mkc.models import KnowledgeObject, ResearchItem

router = APIRouter(prefix="/api/v1/research", tags=["research"])
SessionDep = Annotated[Session, Depends(get_session)]


def _bad_request(code: str, detail: str) -> HTTPException:
    """400 with the standard error envelope."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=knowledge_error_payload(code, detail)["error"]
    )


def _not_found() -> HTTPException:
    """404 with the standard error envelope."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=knowledge_error_payload("not_found", "research item not found")["error"],
    )


def _get_or_404(session: Session, item_id: str) -> ResearchItem:
    """Load by UUID string or raise 404."""
    try:
        parsed = uuid.UUID(item_id)
    except ValueError:
        raise _not_found() from None
    item = session.get(ResearchItem, parsed)
    if item is None:
        raise _not_found()
    return item


def _require_knowledge(session: Session, knowledge_id: str) -> None:
    """404 when knowledge_id does not reference an existing knowledge object."""
    try:
        parsed = uuid.UUID(knowledge_id)
    except ValueError as exc:
        raise _bad_request("invalid_knowledge_id", "knowledge_id must be a UUID") from exc
    if session.get(KnowledgeObject, parsed) is None:
        raise _not_found()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_research_item(payload: ResearchItemIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Create a research item (201)."""
    try:
        payload.validate_against_registry()
    except ValueError as exc:
        raise _bad_request("validation_error", str(exc)) from exc
    _require_knowledge(session, payload.knowledge_id)

    item = ResearchItem(
        knowledge_id=uuid.UUID(payload.knowledge_id),
        title=payload.title,
        topic=payload.topic,
        status=payload.status,
        hypothesis=payload.hypothesis,
        evidence_count=payload.evidence_count,
        validation_level=payload.validation_level,
        related_modules=payload.related_modules,
    )
    session.add(item)
    session.flush()  # assign item.id so the audit row carries the object coordinate
    audit(session, "research.create", token, "research_item", str(item.id), {"title": payload.title})
    session.commit()
    session.refresh(item)
    return {"object": item.to_dict()}


@router.get("")
def list_research_items(
    session: SessionDep,
    token: AuthToken,
    knowledge_id: str | None = Query(default=None, description="filter by parent knowledge object"),
    status_filter: str | None = Query(default=None, alias="status", description="filter by status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PagedResponse:
    """List research items with optional filters and pagination."""
    metrics.inc_search_queries("/api/v1/research")
    stmt = select(ResearchItem)
    if knowledge_id:
        try:
            stmt = stmt.where(ResearchItem.knowledge_id == uuid.UUID(knowledge_id))
        except ValueError as exc:
            raise _bad_request("invalid_knowledge_id", "knowledge_id must be a UUID") from exc
    if status_filter:
        stmt = stmt.where(ResearchItem.status == status_filter)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(stmt.order_by(ResearchItem.id.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return PagedResponse(items=[row.to_dict() for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{research_id}")
def get_research_item(research_id: str, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Research item detail."""
    return {"object": _get_or_404(session, research_id).to_dict()}


@router.patch("/{research_id}")
def update_research_item(
    research_id: str, payload: ResearchItemPatch, session: SessionDep, token: AuthToken
) -> dict[str, Any]:
    """Update mutable fields (all optional)."""
    item = _get_or_404(session, research_id)
    changes: dict[str, Any] = {}
    if payload.title is not None:
        changes["title"] = payload.title
    if payload.topic is not None:
        changes["topic"] = payload.topic
    if payload.status is not None:
        if payload.status not in RESEARCH_STATUSES:
            raise _bad_request(
                "validation_error", f"status must be one of: {', '.join(sorted(RESEARCH_STATUSES))}"
            )
        changes["status"] = payload.status
    if payload.hypothesis is not None:
        changes["hypothesis"] = payload.hypothesis
    if payload.evidence_count is not None:
        changes["evidence_count"] = payload.evidence_count
    if payload.validation_level is not None:
        changes["validation_level"] = payload.validation_level
    if payload.related_modules is not None:
        changes["related_modules"] = payload.related_modules

    for field_name, value in changes.items():
        setattr(item, field_name, value)
    audit(session, "research.update", payload.actor, "research_item", item.id, changes)
    session.commit()
    session.refresh(item)
    return {"object": item.to_dict()}


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_research_item(research_id: str, session: SessionDep, token: AuthToken) -> None:
    """Delete a research item (its knowledge object is unaffected)."""
    item = _get_or_404(session, research_id)
    audit(session, "research.delete", token, "research_item", item.id, {"title": item.title})
    session.delete(item)
    session.commit()
