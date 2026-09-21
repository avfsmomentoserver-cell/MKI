"""Experiment CRUD with an explicit validate flow (human actor required)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mkc.api.metrics import metrics
from mkc.api.schemas import (
    ExperimentIn,
    ExperimentPatch,
    PagedResponse,
    ValidateExperimentIn,
    knowledge_error_payload,
)
from mkc.core.audit import audit
from mkc.core.auth import AuthToken
from mkc.core.constants import EXPERIMENT_STATUSES
from mkc.core.database import get_session
from mkc.core.lifecycle import is_human_actor
from mkc.models import Experiment, KnowledgeObject

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])
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
        detail=knowledge_error_payload("not_found", "experiment not found")["error"],
    )


def _conflict(code: str, detail: str, **extra: Any) -> HTTPException:
    """409 with the standard error envelope."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=knowledge_error_payload(code, detail, **extra)["error"]
    )


def _get_or_404(session: Session, experiment_id: str) -> Experiment:
    """Load by UUID string or raise 404."""
    try:
        parsed = uuid.UUID(experiment_id)
    except ValueError:
        raise _not_found() from None
    experiment = session.get(Experiment, parsed)
    if experiment is None:
        raise _not_found()
    return experiment


def _require_knowledge(session: Session, knowledge_id: str) -> None:
    """404 when knowledge_id does not reference an existing knowledge object."""
    try:
        parsed = uuid.UUID(knowledge_id)
    except ValueError as exc:
        raise _bad_request("invalid_knowledge_id", "knowledge_id must be a UUID") from exc
    if session.get(KnowledgeObject, parsed) is None:
        raise _not_found()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_experiment(payload: ExperimentIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Create an experiment (201)."""
    try:
        payload.validate_against_registry()
    except ValueError as exc:
        raise _bad_request("validation_error", str(exc)) from exc
    _require_knowledge(session, payload.knowledge_id)

    experiment = Experiment(
        knowledge_id=uuid.UUID(payload.knowledge_id),
        title=payload.title,
        hypothesis_tested=payload.hypothesis_tested,
        dataset=payload.dataset,
        method=payload.method,
        result=payload.result,
        statistics_json=payload.statistics_json,
        conclusion=payload.conclusion,
        status=payload.status,
        reproducibility=payload.reproducibility,
        limitations=payload.limitations,
    )
    session.add(experiment)
    session.flush()  # assign experiment.id so the audit row carries the object coordinate
    audit(session, "experiment.create", token, "experiment", str(experiment.id), {"title": payload.title})
    session.commit()
    session.refresh(experiment)
    return {"object": experiment.to_dict()}


@router.get("")
def list_experiments(
    session: SessionDep,
    token: AuthToken,
    knowledge_id: str | None = Query(default=None, description="filter by parent knowledge object"),
    status_filter: str | None = Query(default=None, alias="status", description="filter by status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PagedResponse:
    """List experiments with optional filters and pagination."""
    metrics.inc_search_queries("/api/v1/experiments")
    stmt = select(Experiment)
    if knowledge_id:
        try:
            stmt = stmt.where(Experiment.knowledge_id == uuid.UUID(knowledge_id))
        except ValueError as exc:
            raise _bad_request("invalid_knowledge_id", "knowledge_id must be a UUID") from exc
    if status_filter:
        stmt = stmt.where(Experiment.status == status_filter)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(stmt.order_by(Experiment.id.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return PagedResponse(items=[row.to_dict() for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Experiment detail."""
    return {"object": _get_or_404(session, experiment_id).to_dict()}


@router.patch("/{experiment_id}")
def update_experiment(
    experiment_id: str, payload: ExperimentPatch, session: SessionDep, token: AuthToken
) -> dict[str, Any]:
    """Update mutable fields; validating an experiment must use /validate."""
    experiment = _get_or_404(session, experiment_id)
    changes: dict[str, Any] = {}
    for field_name in (
        "title",
        "hypothesis_tested",
        "dataset",
        "method",
        "result",
        "statistics_json",
        "conclusion",
        "status",
        "reproducibility",
        "limitations",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            changes[field_name] = value
    if "status" in changes:
        if changes["status"] not in EXPERIMENT_STATUSES:
            raise _bad_request(
                "validation_error", f"status must be one of: {', '.join(sorted(EXPERIMENT_STATUSES))}"
            )
        if changes["status"] == "validated" and experiment.status != "validated":
            raise _conflict("use_validate_endpoint", "use POST /experiments/{id}/validate to validate")

    for field_name, value in changes.items():
        setattr(experiment, field_name, value)
    audit(session, "experiment.update", payload.actor, "experiment", experiment.id, changes)
    session.commit()
    session.refresh(experiment)
    return {"object": experiment.to_dict()}


@router.post("/{experiment_id}/validate")
def validate_experiment(
    experiment_id: str, payload: ValidateExperimentIn, session: SessionDep, token: AuthToken
) -> dict[str, Any]:
    """Mark an experiment validated. Requires a human actor (409 otherwise)."""
    experiment = _get_or_404(session, experiment_id)
    if not is_human_actor(payload.actor):
        raise _conflict(
            "human_actor_required",
            f"validating an experiment requires a human actor (got automated actor {payload.actor!r})",
        )
    previous = experiment.status
    experiment.status = "validated"
    audit(
        session,
        "experiment.validate",
        payload.actor,
        "experiment",
        experiment.id,
        {"from_status": previous, "notes": payload.notes},
    )
    session.commit()
    session.refresh(experiment)
    return {"object": experiment.to_dict()}


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experiment(experiment_id: str, session: SessionDep, token: AuthToken) -> None:
    """Delete an experiment row (failed experiments keep their provenance via audit_log)."""
    experiment = _get_or_404(session, experiment_id)
    audit(session, "experiment.delete", token, "experiment", experiment.id, {"title": experiment.title})
    session.delete(experiment)
    session.commit()
