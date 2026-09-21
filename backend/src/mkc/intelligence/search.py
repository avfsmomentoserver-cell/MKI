"""Full-text search over the MKC registry (house stack: SQLAlchemy ILIKE only).

Contract (consumed by ``api/routers/search.py`` and the ``mkc search`` CLI):

- :func:`search_knowledge` — search ``KnowledgeObject`` rows.
- :func:`search_documents` — search ``Document`` rows (same result shape).

Shared semantics:

- the query is tokenised on whitespace; **every** token must match
  (AND semantics) in ``title`` or ``body`` (case-insensitive,
  parameterised ``ILIKE`` — user input never reaches the SQL string);
- optional filters: knowledge types, lifecycle states, source types
  (via the registered ``Source`` row), and an inclusive ``created_at``
  window (``date_from`` / ``date_to``; a bare date covers the whole day);
- results are deterministic: ``created_at desc, id``;
- pagination honours ``mkc.api.schemas.MAX_PAGE_SIZE``;
- each result carries id, title, type, lifecycle_state, source_type,
  ``snippet`` (±100 chars around the first match), confidence, and a
  provenance **summary** (source_type / source_id / source_location —
  never the full ``original_text``).

``ValueError`` is raised on an empty query or out-of-range pagination;
callers map it to 422 (API) or a CLI error message.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from mkc.api.schemas import MAX_PAGE_SIZE
from mkc.models import Document, KnowledgeObject, Source

DEFAULT_PAGE_SIZE = 20
#: Characters of context kept on each side of the first match in a snippet.
SNIPPET_RADIUS = 100
_TOKEN_RE = re.compile(r"\S+")


def _tokenize(query: str) -> list[str]:
    """Whitespace-split the query (stable order; AND semantics need all tokens)."""
    return _TOKEN_RE.findall(query or "")


def _clean(value: str | None) -> str:
    """Collapse whitespace runs for readable snippets."""
    return re.sub(r"\s+", " ", (value or "")).strip()


def _snippet(title: str, body: str, tokens: list[str]) -> str:
    """±100 chars around the first occurrence of the first matched token."""
    lowered_title = title.lower()
    lowered_body = body.lower()
    for token in tokens:
        needle = token.lower()
        index = lowered_title.find(needle)
        if index >= 0:
            return _clean(title[max(0, index - SNIPPET_RADIUS) : index + SNIPPET_RADIUS + 100])
        index = lowered_body.find(needle)
        if index >= 0:
            return _clean(body[max(0, index - SNIPPET_RADIUS) : index + SNIPPET_RADIUS + 100])
    return _clean(f"{title} {body}")[: 2 * SNIPPET_RADIUS + 100]


def _coerce_strings(value: str | Iterable[str] | None) -> tuple[str, ...] | None:
    """Normalise a str-or-list filter value to a tuple of non-empty strings."""
    if value is None:
        return None
    if isinstance(value, str):
        return (value,) if value else None
    cleaned = tuple(item for item in value if item)
    return cleaned or None


def _parse_datetime(value: date | datetime | str) -> datetime:
    """Accept an ISO datetime string or date; naive values are treated as UTC."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _created_at_clause(model: Any, value: date | datetime | str, *, end_of_day: bool) -> Any:
    """One inclusive bound on ``created_at`` (a bare date covers the whole day)."""
    parsed = _parse_datetime(value)
    if end_of_day and (parsed.hour, parsed.minute, parsed.second, parsed.microsecond) == (0, 0, 0, 0):
        return model.created_at < parsed + timedelta(days=1)
    return model.created_at >= parsed


@dataclass(frozen=True)
class SearchQuery:
    """Normalised, validated search parameters shared by both search functions."""

    tokens: tuple[str, ...]
    types: tuple[str, ...] | None
    states: tuple[str, ...] | None
    source_types: tuple[str, ...] | None
    date_from: date | datetime | str | None
    date_to: date | datetime | str | None
    page: int
    page_size: int


def _normalise(
    query: str,
    *,
    types: str | Iterable[str] | None = None,
    states: str | Iterable[str] | None = None,
    source_types: str | Iterable[str] | None = None,
    date_from: date | datetime | str | None = None,
    date_to: date | datetime | str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> SearchQuery:
    tokens = tuple(_tokenize(query))
    if not tokens:
        raise ValueError("query must contain at least one token")
    if page < 1:
        raise ValueError("page must be >= 1")
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be <= {MAX_PAGE_SIZE}")
    return SearchQuery(
        tokens=tokens,
        types=_coerce_strings(types),
        states=_coerce_strings(states),
        source_types=_coerce_strings(source_types),
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


def _apply_knowledge_filters(stmt: Any, norm: SearchQuery) -> Any:
    """Token AND-match on title/body plus the optional knowledge filters."""
    clauses: list[Any] = []
    for token in norm.tokens:
        like = f"%{token}%"
        clauses.append(or_(KnowledgeObject.title.ilike(like), KnowledgeObject.body.ilike(like)))
    stmt = stmt.where(and_(*clauses))
    if norm.types:
        stmt = stmt.where(KnowledgeObject.type.in_(norm.types))
    if norm.states:
        stmt = stmt.where(KnowledgeObject.lifecycle_state.in_(norm.states))
    if norm.source_types:
        stmt = stmt.where(
            KnowledgeObject.source_id.in_(
                select(Source.id).where(Source.source_type.in_(norm.source_types))
            )
        )
    if norm.date_from is not None:
        stmt = stmt.where(_created_at_clause(KnowledgeObject, norm.date_from, end_of_day=False))
    if norm.date_to is not None:
        stmt = stmt.where(_created_at_clause(KnowledgeObject, norm.date_to, end_of_day=True))
    return stmt


def _apply_document_filters(stmt: Any, norm: SearchQuery) -> Any:
    """Token AND-match on title (documents carry no body) + document filters.

    ``states`` is accepted for a uniform contract and ignored: documents
    have no lifecycle. ``types`` filters ``doc_type``.
    """
    clauses: list[Any] = [Document.title.ilike(f"%{token}%") for token in norm.tokens]
    stmt = stmt.where(and_(*clauses))
    if norm.types:
        stmt = stmt.where(Document.doc_type.in_(norm.types))
    if norm.source_types:
        stmt = stmt.where(
            Document.source_id.in_(select(Source.id).where(Source.source_type.in_(norm.source_types)))
        )
    if norm.date_from is not None:
        stmt = stmt.where(_created_at_clause(Document, norm.date_from, end_of_day=False))
    if norm.date_to is not None:
        stmt = stmt.where(_created_at_clause(Document, norm.date_to, end_of_day=True))
    return stmt


def _serialize_result(
    row: Any,
    *,
    kind: str,
    snippet: str,
    provenance: dict[str, Any],
    source_type: str,
) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "kind": kind,
        "title": row.title,
        "type": row.type if kind == "knowledge" else row.doc_type,
        "lifecycle_state": row.lifecycle_state if kind == "knowledge" else None,
        "source_type": source_type,
        "snippet": snippet,
        "confidence": row.confidence if kind == "knowledge" else None,
        "provenance": provenance,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _source_index(session: Session) -> dict[str, Source]:
    """All registered sources keyed by stringified UUID (small table, one pass)."""
    return {str(source.id): source for source in session.execute(select(Source)).scalars().all()}


def _search_rows(
    session: Session,
    stmt: Any,
    *,
    created_at_desc: Any,
    id_column: Any,
    norm: SearchQuery,
) -> tuple[int, list[Any]]:
    """Count + page slice with the deterministic ordering (created_at desc, id)."""
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.execute(
            stmt.order_by(created_at_desc, id_column)
            .offset((norm.page - 1) * norm.page_size)
            .limit(norm.page_size)
        )
        .scalars()
        .all()
    )
    return total, list(rows)


def _common_kwargs(
    *,
    types: str | Iterable[str] | None,
    states: str | Iterable[str] | None,
    source_types: str | Iterable[str] | None,
    date_from: date | datetime | str | None,
    date_to: date | datetime | str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    return {
        "types": types,
        "states": states,
        "source_types": source_types,
        "date_from": date_from,
        "date_to": date_to,
        "page": page,
        "page_size": page_size,
    }


def search_knowledge(
    session: Session,
    query: str,
    *,
    types: str | Iterable[str] | None = None,
    states: str | Iterable[str] | None = None,
    source_types: str | Iterable[str] | None = None,
    date_from: date | datetime | str | None = None,
    date_to: date | datetime | str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Search knowledge objects; every token must match title or body (AND).

    Returns ``{"query", "total", "page", "page_size", "results"}``. Raises
    ``ValueError`` on an empty query or out-of-range pagination.
    """
    norm = _normalise(query, **_common_kwargs(
        types=types, states=states, source_types=source_types,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    ))
    stmt = _apply_knowledge_filters(select(KnowledgeObject), norm)
    total, rows = _search_rows(
        session, stmt,
        created_at_desc=KnowledgeObject.created_at.desc(),
        id_column=KnowledgeObject.id,
        norm=norm,
    )
    sources = _source_index(session) if rows else {}
    results = []
    for row in rows:
        prov = row.provenance or {}
        source = sources.get(str(row.source_id)) if row.source_id else None
        results.append(_serialize_result(
            row,
            kind="knowledge",
            snippet=_snippet(row.title, row.body, list(norm.tokens)),
            provenance={
                "source_type": prov.get("source_type") or "",
                "source_id": prov.get("source_id") or "",
                "source_location": prov.get("source_location") or "",
            },
            source_type=source.source_type if source else "",
        ))
    return {
        "query": query,
        "total": total,
        "page": norm.page,
        "page_size": norm.page_size,
        "results": results,
    }


def search_documents(
    session: Session,
    query: str,
    *,
    types: str | Iterable[str] | None = None,
    states: str | Iterable[str] | None = None,
    source_types: str | Iterable[str] | None = None,
    date_from: date | datetime | str | None = None,
    date_to: date | datetime | str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Search document rows (same envelope as :func:`search_knowledge`).

    Documents carry no ``body`` column, so tokens match ``title`` only.
    """
    norm = _normalise(query, **_common_kwargs(
        types=types, states=states, source_types=source_types,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    ))
    stmt = _apply_document_filters(select(Document), norm)
    total, rows = _search_rows(
        session, stmt,
        created_at_desc=Document.created_at.desc(),
        id_column=Document.id,
        norm=norm,
    )
    sources = _source_index(session) if rows else {}
    results = []
    for row in rows:
        source = sources.get(str(row.source_id)) if row.source_id else None
        results.append(_serialize_result(
            row,
            kind="document",
            snippet=_snippet(row.title, row.title, list(norm.tokens)),
            provenance={
                "source_type": source.source_type if source else "",
                "source_id": source.source_id if source else "",
                "source_location": row.file_path,
            },
            source_type=source.source_type if source else "",
        ))
    return {
        "query": query,
        "total": total,
        "page": norm.page,
        "page_size": norm.page_size,
        "results": results,
    }
