"""Knowledge object CRUD with lifecycle-validated transitions.

Contract:

- ``POST /api/v1/knowledge``: create; provenance.source_location required.
- ``GET  /api/v1/knowledge``: list with type / lifecycle_state / status /
  q filters and ``page`` / ``page_size`` pagination (stable ordering by
  created_at desc, id desc).
- ``GET  /api/v1/knowledge/{id}``: detail incl. the full provenance chain.
- ``PATCH /api/v1/knowledge/{id}``: field updates; lifecycle_state changes
  go through the state machine (409 + allowed next states on violation);
  provenance is immutable and cannot be modified here.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from mkc.api.metrics import metrics
from mkc.api.schemas import KnowledgeIn, KnowledgePatch, PagedResponse, knowledge_error_payload
from mkc.core.audit import audit
from mkc.core.auth import AuthToken
from mkc.core.constants import KNOWLEDGE_STATUSES, LIFECYCLE_STATES
from mkc.core.database import get_session
from mkc.core.lifecycle import allowed_next_states, validate_transition
from mkc.models import KnowledgeObject, Source

logger = logging.getLogger("mkc.api.knowledge")

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
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
        detail=knowledge_error_payload("not_found", "knowledge object not found")["error"],
    )


def _get_or_404(session: Session, object_id: str) -> KnowledgeObject:
    """Load by UUID string or raise 404 (malformed ids are 404, not 400: no oracle)."""
    try:
        parsed = uuid.UUID(object_id)
    except ValueError:
        raise _not_found() from None
    obj = session.get(KnowledgeObject, parsed)
    if obj is None:
        raise _not_found()
    return obj


@router.post("", status_code=status.HTTP_201_CREATED)
def create_knowledge(payload: KnowledgeIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Create a knowledge object (201). Provenance without source_location -> 400."""
    try:
        payload.validate_against_registry()
    except ValueError as exc:
        raise _bad_request("validation_error", str(exc)) from exc

    parsed_source = None
    if payload.source_id is not None:
        try:
            parsed_source = uuid.UUID(payload.source_id)
        except ValueError as exc:
            raise _bad_request("invalid_source_id", "source_id must be a UUID") from exc
        if session.get(Source, parsed_source) is None:
            raise _bad_request("unknown_source", "source_id does not reference a registered source")

    obj = KnowledgeObject(
        type=payload.type,
        title=payload.title,
        content_summary=payload.content_summary,
        body=payload.body,
        lifecycle_state=payload.lifecycle_state,
        confidence=payload.confidence,
        source_id=parsed_source,
        provenance=payload.provenance,
        status=payload.status,
    )
    session.add(obj)
    session.flush()  # assign obj.id so the audit row carries the object coordinate
    audit(
        session,
        "knowledge.create",
        token,
        "knowledge_object",
        str(obj.id),
        {"title": payload.title, "type": payload.type, "lifecycle_state": payload.lifecycle_state},
    )
    session.commit()
    session.refresh(obj)
    logger.info("created knowledge object %s (%s)", obj.id, obj.title)
    return {"object": obj.to_dict()}


@router.get("")
def list_knowledge(
    session: SessionDep,
    token: AuthToken,
    type: str | None = Query(default=None, description="filter by knowledge type"),
    lifecycle_state: str | None = Query(default=None, description="filter by lifecycle state"),
    status_filter: str | None = Query(default=None, alias="status", description="filter by active/archived"),
    q: str | None = Query(default=None, description="substring match on title/summary"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PagedResponse:
    """List knowledge objects with filters and stable pagination."""
    metrics.inc_search_queries("/api/v1/knowledge")
    stmt = select(KnowledgeObject)
    if type:
        stmt = stmt.where(KnowledgeObject.type == type)
    if lifecycle_state:
        stmt = stmt.where(KnowledgeObject.lifecycle_state == lifecycle_state)
    if status_filter:
        stmt = stmt.where(KnowledgeObject.status == status_filter)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(KnowledgeObject.title.ilike(like), KnowledgeObject.content_summary.ilike(like)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(
            stmt.order_by(KnowledgeObject.created_at.desc(), KnowledgeObject.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PagedResponse(items=[row.to_dict() for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{knowledge_id}")
def get_knowledge(knowledge_id: str, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Detail view incl. the full provenance chain (object + registered source)."""
    obj = _get_or_404(session, knowledge_id)
    data = obj.to_dict()
    source = session.get(Source, obj.source_id) if obj.source_id else None
    data["source"] = source.to_dict() if source else None
    data["provenance_chain"] = {
        "object": data["provenance"],
        "source": source.to_dict() if source else None,
    }
    return {"object": data}


@router.patch("/{knowledge_id}")
def update_knowledge(
    knowledge_id: str, payload: KnowledgePatch, session: SessionDep, token: AuthToken
) -> dict[str, Any]:
    """Update mutable fields; lifecycle changes are state-machine validated.

    Invalid transitions return 409 with the reason and the allowed next
    states. Every accepted change is written to audit_log.
    """
    obj = _get_or_404(session, knowledge_id)
    from_state = obj.lifecycle_state
    changes: dict[str, Any] = {}

    if payload.title is not None:
        changes["title"] = payload.title
    if payload.content_summary is not None:
        changes["content_summary"] = payload.content_summary
    if payload.body is not None:
        changes["body"] = payload.body
    if payload.confidence is not None:
        changes["confidence"] = payload.confidence
    if payload.status is not None:
        if payload.status not in KNOWLEDGE_STATUSES:
            raise _bad_request(
                "validation_error", f"status must be one of: {', '.join(sorted(KNOWLEDGE_STATUSES))}"
            )
        changes["status"] = payload.status

    if payload.lifecycle_state is not None:
        if payload.lifecycle_state not in LIFECYCLE_STATES:
            raise _bad_request("validation_error", f"unknown lifecycle_state {payload.lifecycle_state!r}")
        if payload.lifecycle_state == obj.lifecycle_state:
            raise _conflict(
                obj.lifecycle_state,
                payload.lifecycle_state,
                "state unchanged (self-transitions are rejected)",
            )
        result = validate_transition(obj.lifecycle_state, payload.lifecycle_state, actor=payload.actor)
        if not result.allowed:
            raise _conflict(obj.lifecycle_state, payload.lifecycle_state, result.reason)
        changes["lifecycle_state"] = payload.lifecycle_state

    for field_name, value in changes.items():
        setattr(obj, field_name, value)

    details: dict[str, Any] = dict(changes)
    if "lifecycle_state" in changes:
        details["from_state"] = from_state

    audit(
        session,
        "knowledge.update" if "lifecycle_state" not in changes else "knowledge.lifecycle_transition",
        payload.actor,
        "knowledge_object",
        obj.id,
        details,
    )
    session.commit()
    session.refresh(obj)
    return {"object": obj.to_dict()}


def _conflict(from_state: str, to_state: str, reason: str) -> HTTPException:
    """409 with the reason plus the allowed next states from from_state."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=knowledge_error_payload(
            "invalid_transition",
            reason,
            from_state=from_state,
            to_state=to_state,
            allowed_next_states=allowed_next_states(from_state),
        )["error"],
    )
