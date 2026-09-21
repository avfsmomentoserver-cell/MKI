"""Decision CRUD with an explicit supersede flow (decisions are never overwritten)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mkc.api.metrics import metrics
from mkc.api.schemas import DecisionIn, DecisionPatch, PagedResponse, SupersedeIn, knowledge_error_payload
from mkc.core.audit import audit
from mkc.core.auth import AuthToken
from mkc.core.constants import DECISION_STATUSES
from mkc.core.database import get_session
from mkc.models import Decision, KnowledgeObject

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])
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
        detail=knowledge_error_payload("not_found", "decision not found")["error"],
    )


def _conflict(code: str, detail: str, **extra: Any) -> HTTPException:
    """409 with the standard error envelope."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=knowledge_error_payload(code, detail, **extra)["error"]
    )


def _get_or_404(session: Session, decision_id: str) -> Decision:
    """Load by UUID string or raise 404."""
    try:
        parsed = uuid.UUID(decision_id)
    except ValueError:
        raise _not_found() from None
    decision = session.get(Decision, parsed)
    if decision is None:
        raise _not_found()
    return decision


def _require_knowledge(session: Session, knowledge_id: str) -> None:
    """404 when knowledge_id does not reference an existing knowledge object."""
    try:
        parsed = uuid.UUID(knowledge_id)
    except ValueError as exc:
        raise _bad_request("invalid_knowledge_id", "knowledge_id must be a UUID") from exc
    if session.get(KnowledgeObject, parsed) is None:
        raise _not_found()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_decision(payload: DecisionIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Record a decision (201)."""
    try:
        payload.validate_against_registry()
    except ValueError as exc:
        raise _bad_request("validation_error", str(exc)) from exc
    _require_knowledge(session, payload.knowledge_id)

    decision = Decision(
        knowledge_id=uuid.UUID(payload.knowledge_id),
        title=payload.title,
        context=payload.context,
        problem=payload.problem,
        alternatives=payload.alternatives,
        decision_text=payload.decision_text,
        reason=payload.reason,
        evidence=payload.evidence,
        affected_components=payload.affected_components,
        status=payload.status,
        author=payload.author,
        decided_at=payload.decided_at,
    )
    session.add(decision)
    session.flush()  # assign decision.id so the audit row carries the object coordinate
    audit(
        session,
        "decision.create",
        token,
        "decision",
        str(decision.id),
        {"title": payload.title, "status": payload.status},
    )
    session.commit()
    session.refresh(decision)
    return {"object": decision.to_dict()}


@router.get("")
def list_decisions(
    session: SessionDep,
    token: AuthToken,
    knowledge_id: str | None = Query(default=None, description="filter by parent knowledge object"),
    status_filter: str | None = Query(default=None, alias="status", description="filter by status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PagedResponse:
    """List decisions with optional filters and pagination."""
    metrics.inc_search_queries("/api/v1/decisions")
    stmt = select(Decision)
    if knowledge_id:
        try:
            stmt = stmt.where(Decision.knowledge_id == uuid.UUID(knowledge_id))
        except ValueError as exc:
            raise _bad_request("invalid_knowledge_id", "knowledge_id must be a UUID") from exc
    if status_filter:
        stmt = stmt.where(Decision.status == status_filter)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(stmt.order_by(Decision.id.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return PagedResponse(items=[row.to_dict() for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{decision_id}")
def get_decision(decision_id: str, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Decision detail."""
    return {"object": _get_or_404(session, decision_id).to_dict()}


@router.patch("/{decision_id}")
def update_decision(
    decision_id: str, payload: DecisionPatch, session: SessionDep, token: AuthToken
) -> dict[str, Any]:
    """Update mutable fields; a superseded decision only changes status via /supersede."""
    decision = _get_or_404(session, decision_id)
    if decision.status == "superseded":
        raise _conflict(
            "superseded_immutable", "a superseded decision is immutable; create a new decision instead"
        )
    changes: dict[str, Any] = {}
    for field_name in (
        "context",
        "problem",
        "alternatives",
        "decision_text",
        "reason",
        "evidence",
        "affected_components",
        "author",
        "decided_at",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            changes[field_name] = value
    if payload.status is not None:
        if payload.status not in DECISION_STATUSES:
            raise _bad_request(
                "validation_error", f"status must be one of: {', '.join(sorted(DECISION_STATUSES))}"
            )
        if payload.status == "superseded":
            raise _conflict("use_supersede_endpoint", "use POST /decisions/{id}/supersede to supersede")
        changes["status"] = payload.status

    for field_name, value in changes.items():
        setattr(decision, field_name, value)
    audit(session, "decision.update", payload.actor, "decision", decision.id, changes)
    session.commit()
    session.refresh(decision)
    return {"object": decision.to_dict()}


@router.post("/{decision_id}/supersede")
def supersede_decision(
    decision_id: str, payload: SupersedeIn, session: SessionDep, token: AuthToken
) -> dict[str, Any]:
    """Mark a decision superseded (200). The original is never overwritten."""
    decision = _get_or_404(session, decision_id)
    if decision.status == "superseded":
        raise _conflict("already_superseded", "decision is already superseded")
    decision.status = "superseded"
    audit(
        session,
        "decision.supersede",
        payload.actor,
        "decision",
        decision.id,
        {"superseded_by": payload.superseded_by, "reason": payload.reason},
    )
    session.commit()
    session.refresh(decision)
    return {"object": decision.to_dict()}


@router.delete("/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(decision_id: str, session: SessionDep, token: AuthToken) -> None:
    """Delete a decision row (hard delete; prefer /supersede for real history)."""
    decision = _get_or_404(session, decision_id)
    audit(session, "decision.delete", token, "decision", decision.id, {"title": decision.title})
    session.delete(decision)
    session.commit()
