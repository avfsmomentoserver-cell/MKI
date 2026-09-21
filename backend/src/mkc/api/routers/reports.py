"""Report endpoints for the MKC registry.

Contract:

- ``GET  /api/v1/reports``: list generated ``Report`` rows (newest first),
  paged.
- ``GET  /api/v1/reports/{report_id}``: fetch a report **by its DB UUID
  only**. ``report_id`` is parsed as a UUID and looked up in the
  ``reports`` table; a raw filesystem path in the URL is never accepted
  (threat-model item T-P5: no path traversal, no arbitrary file reads).
  The response includes the markdown content only when the stored file
  still exists on disk.
- ``POST /api/v1/reports/generate``: run report generation in-process for
  a supported ``report_type`` and return the upserted ``Report`` row.
  Path is always the generator's own output file — callers cannot choose
  where reports are written.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mkc.api.schemas import PagedResponse, knowledge_error_payload
from mkc.core.audit import audit
from mkc.core.auth import AuthToken
from mkc.core.database import get_session
from mkc.intelligence.reports.generator import SUPPORTED_REPORT_TYPES, generate_report
from mkc.models import Report

logger = logging.getLogger("mkc.api.reports")

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
SessionDep = Annotated[Session, Depends(get_session)]


def _bad_request(code: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=knowledge_error_payload(code, detail)["error"],
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=knowledge_error_payload("not_found", "report not found")["error"],
    )


def _get_or_404(session: Session, report_id: str) -> Report:
    """Load by DB UUID; malformed ids are 404 (no id oracle)."""
    try:
        parsed = uuid.UUID(report_id)
    except ValueError:
        raise _not_found() from None
    row = session.get(Report, parsed)
    if row is None:
        raise _not_found()
    return row


@router.get("")
def list_reports(
    session: SessionDep,
    token: AuthToken,
    type: str | None = Query(default=None, description="filter by report type"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PagedResponse:
    """List generated reports, newest first."""
    stmt = select(Report)
    if type:
        stmt = stmt.where(Report.type == type)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(
            stmt.order_by(Report.generated_at.desc(), Report.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PagedResponse(items=[row.to_dict() for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{report_id}")
def get_report(report_id: str, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Fetch one report by DB UUID (never by filesystem path)."""
    row = _get_or_404(session, report_id)
    data = row.to_dict()
    # The markdown file is an implementation detail: include it only when the
    # stored path is still a readable file we generated ourselves.
    try:
        from pathlib import Path

        file_path = Path(row.path)
        if file_path.is_file():
            data["markdown"] = file_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        data["markdown"] = None
    return {"report": data}


class ReportGenerateIn(BaseModel):
    """Body for POST /api/v1/reports/generate."""

    report_type: Literal["project-knowledge", "research-gaps", "implementation-plan"] = Field(
        description="one of " + ", ".join(SUPPORTED_REPORT_TYPES)
    )
    actor: str = Field(default="api", description="who triggered the generation (audited)")


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate(payload: ReportGenerateIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Generate a report in-process and return the upserted Report row."""
    try:
        row = generate_report(session, payload.report_type)
    except ValueError as exc:
        raise _bad_request("validation_error", str(exc)) from exc
    audit(session, "report.generate", payload.actor, "report", row.id, {"type": row.type, "path": row.path})
    session.commit()
    logger.info("generated report %s (%s)", row.id, row.type)
    return {"report": row.to_dict()}
