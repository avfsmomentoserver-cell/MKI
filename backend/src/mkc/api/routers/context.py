"""AI Context routes: egress-gated context packs over the knowledge registry.

Contract (delegates all work to :class:`mkc.intelligence.context.ContextService`):

- ``GET /api/v1/context/{topic}``: context pack for *topic* — relevant
  decisions/research/experiments/knowledge objects, related code paths,
  open questions, and a strict split of ``validated_facts`` (lifecycle in
  validated/implemented/production) vs ``speculative_conclusions``
  (everything else). Every item carries its provenance (incl. derived
  ``origin_trust``) and the pack carries the standing disclaimer note.
  A topic with no matches returns 200 with empty lists and the note
  "No indexed knowledge found for topic." (a blank topic is rejected by
  the service and yields the same empty-pack shape).
- ``GET /api/v1/context/architecture``: architecture overview compiled
  from entity modules and their relations.
- ``POST /api/v1/context/query``: body ``{"query", "top_k"}`` -> the same
  pack shape for *query*.

All routes require ``Authorization: Bearer <MKC_API_TOKEN>``.
The router is deliberately thin: no registry logic lives here.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mkc.core.auth import AuthToken
from mkc.core.database import get_session
from mkc.intelligence.context import ContextService

logger = logging.getLogger("mkc.api.context")

router = APIRouter(prefix="/api/v1/context", tags=["context"])
SessionDep = Annotated[Session, Depends(get_session)]

#: Returned (HTTP 200) when a topic/query matches nothing — empty pack,
#: explicit note. Mirrors the service pack's list/manifest keys.
EMPTY_PACK_NOTE = "No indexed knowledge found for topic."

_service = ContextService()


def _empty_pack(topic: str) -> dict[str, Any]:
    """Context-pack-shaped 200 body for a topic with no indexed knowledge."""
    return {
        "topic": topic,
        "relevant_decisions": [],
        "relevant_research": [],
        "relevant_experiments": [],
        "relevant_objects": [],
        "related_code_paths": [],
        "open_questions": [],
        "validated_facts": [],
        "speculative_conclusions": [],
        "provenance": {"items": 0, "quarantined": 0, "origin_trust_counts": {}, "notes": ""},
        "egress_manifest": {
            "private_sources_included": [],
            "quarantined_included": False,
            "quarantined_suppressed": 0,
            "quarantined_ids": [],
            "private_source_ids": [],
            "policies": [],
        },
        "quarantine_banner": None,
        "note": EMPTY_PACK_NOTE,
        "summary": {
            "relevant_decisions": 0,
            "relevant_research": 0,
            "relevant_experiments": 0,
            "relevant_objects": 0,
            "related_code_paths": 0,
            "open_questions": 0,
            "validated_facts": 0,
            "speculative_conclusions": 0,
            "quarantined_suppressed": 0,
        },
    }


@router.get("")
def empty_topic_context(session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """No topic given -> 200 empty pack (``/api/v1/context`` and ``/.../context/``)."""
    return _empty_pack("")


@router.get("/architecture")
def architecture_overview(session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Architecture overview: entity modules + relations (read-only)."""
    return _service.build_architecture_overview(session)


@router.get("/{topic}")
def get_context_pack(topic: str, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Context pack for *topic* (blank topics yield the empty-pack shape)."""
    try:
        return _service.build_context_pack(session, topic)
    except ValueError:
        return _empty_pack(topic)


class ContextQueryIn(BaseModel):
    """Body for POST /api/v1/context/query."""

    query: str = Field(default="", max_length=512, description="topic text to compile context for")
    # Accepted for forward compatibility; the rule-based service compiles all
    # matching knowledge (list sections are capped server-side), so top_k is
    # not yet used to truncate sections.
    top_k: int = Field(default=20, ge=1, le=100)


@router.post("/query")
def query_context(payload: ContextQueryIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Context pack for ``payload.query`` (same pack shape as GET)."""
    try:
        return _service.build_context_pack(session, payload.query)
    except ValueError:
        return _empty_pack(payload.query)
