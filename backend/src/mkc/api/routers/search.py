"""Search endpoint over the MKC knowledge registry.

Contract:

- ``POST /api/v1/search``: AND-token search over knowledge objects and/or
  documents, delegating to :mod:`mkc.intelligence.search` (same semantics
  as the CLI: ILIKE per token, optional filters, ``MAX_PAGE_SIZE`` cap).

Request body (all optional except ``query``):

- ``query``: required field; may be empty or whitespace-only, in which case
  the endpoint returns 200 with zero results (a search with no tokens
  matches nothing — it is not an error).
- ``scope``: ``knowledge`` (default) | ``documents`` | ``all``.
- ``types``: list of knowledge types / doc types.
- ``lifecycle_states``: list of lifecycle states (knowledge only).
- ``sources``: list of source types (git, markdown, chatgpt, ...).
- ``page`` / ``page_size``: pagination (``page_size`` <= MAX_PAGE_SIZE).

Response: ``{"query", "total", "page", "page_size", "results": [...]}``
where each result carries id / kind / title / type / lifecycle_state /
confidence / snippet / provenance (source_type, source_id, source_location).
``scope=all`` merges both scopes (knowledge first, then documents).

Errors: 422 for out-of-range pagination (``intelligence.search`` raises
``ValueError``; mapped here). An empty/whitespace query is NOT an error:
it returns 200 with zero results.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mkc.api.metrics import metrics
from mkc.api.schemas import MAX_PAGE_SIZE, knowledge_error_payload
from mkc.core.auth import AuthToken
from mkc.core.database import get_session
from mkc.intelligence.search import search_documents, search_knowledge

logger = logging.getLogger("mkc.api.search")

router = APIRouter(prefix="/api/v1/search", tags=["search"])
SessionDep = Annotated[Session, Depends(get_session)]


class SearchIn(BaseModel):
    """Body for POST /api/v1/search."""

    query: str = Field(min_length=1, max_length=512, description="space-separated AND tokens")
    scope: Literal["knowledge", "documents", "all"] = Field(default="knowledge")
    types: list[str] | None = Field(
        default=None, description="knowledge types (knowledge scope) or doc types (documents scope)"
    )
    lifecycle_states: list[str] | None = Field(default=None, description="knowledge lifecycle states (ignored for documents)")
    sources: list[str] | None = Field(default=None, description="registered source types (git, markdown, chatgpt, ...)")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)

    def validate_search(self) -> None:
        """Raise ValueError on a whitespace-only query."""
        if not self.query.strip():
            raise ValueError("query must contain at least one non-empty token")


@router.post("")
def search(payload: SearchIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Run the registry search (read-only). See module docstring for the contract."""
    metrics.inc_search_queries("/api/v1/search")
    try:
        payload.validate_search()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=knowledge_error_payload("validation_error", str(exc))["error"],
        ) from exc

    common = dict(
        types=payload.types,
        states=payload.lifecycle_states,
        source_types=payload.sources,
        page=payload.page,
        page_size=payload.page_size,
    )
    try:
        knowledge = search_knowledge(session, payload.query, **common) if payload.scope in {"knowledge", "all"} else None
        documents = search_documents(session, payload.query, **common) if payload.scope in {"documents", "all"} else None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=knowledge_error_payload("validation_error", str(exc))["error"],
        ) from exc

    if payload.scope == "knowledge":
        return knowledge
    if payload.scope == "documents":
        return documents
    # scope == "all": both queries were executed above.
    return {
        "query": payload.query,
        "total": knowledge["total"] + documents["total"],
        "page": knowledge["page"],
        "page_size": knowledge["page_size"],
        "results": list(knowledge["results"]) + list(documents["results"]),
        "knowledge_total": knowledge["total"],
        "documents_total": documents["total"],
    }
