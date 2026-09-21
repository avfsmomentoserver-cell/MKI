"""Audit trail helper: one shape for every mutation across the API layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from mkc.models import AuditLog


def audit(
    session: Session,
    action: str,
    actor: str,
    object_type: str,
    object_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append one row to ``audit_log`` (does not commit; the caller commits).

    Central helper so every mutation lands in the trail in exactly the same
    shape: action verb, actor identity, object coordinates, JSON details.
    """
    session.add(
        AuditLog(
            action=action,
            actor=actor,
            object_type=object_type,
            object_id=str(object_id),
            details=details or {},
        )
    )
