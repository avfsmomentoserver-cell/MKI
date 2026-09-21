"""Ingestion endpoint: run the matching collector in-process.

Contract:

- ``POST /api/v1/ingest``: body ``{"source_type", "path"}`` where
  ``source_type`` is ``git`` | ``markdown`` | ``chatgpt``. The path must be
  a local directory (git: a repository root; markdown: a directory of
  ``.md`` files; chatgpt: a directory of JSON conversation exports).

  The matching collector runs synchronously in the API process and the
  response is the ``IngestionResult`` summary (files indexed, documents
  created/refreshed, commits indexed, per-file errors, duration). This is
  intended for local/ops use against a trusted corpus — large repos make
  the request slow, and there is no background queue in this deployment.

  The path is resolved and used read-only by the collector; a path that
  does not exist or is not a directory yields 422.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mkc.api.metrics import metrics
from mkc.api.schemas import knowledge_error_payload
from mkc.core.audit import audit
from mkc.core.auth import AuthToken
from mkc.core.database import get_session
from mkc.intelligence.ingest.base import IngestionResult
from mkc.intelligence.ingest.chatgpt_importer import ChatGPTImporter
from mkc.intelligence.ingest.git_collector import GitRepoCollector
from mkc.intelligence.ingest.markdown_collector import MarkdownCollector

logger = logging.getLogger("mkc.api.ingest")

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
SessionDep = Annotated[Session, Depends(get_session)]


class IngestIn(BaseModel):
    """Body for POST /api/v1/ingest."""

    source_type: Literal["git", "markdown", "chatgpt"] = Field(description="collector to run")
    path: str = Field(min_length=1, max_length=1024, description="local directory of the source")
    actor: str = Field(default="api", description="who triggered the ingestion (audited)")


def _bad_request(code: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=knowledge_error_payload(code, detail)["error"],
    )


def _run_collector(source_type: str, path: Path) -> IngestionResult:
    """Instantiate and run the collector matching *source_type* (read-only)."""
    if source_type == "git":
        return GitRepoCollector(path).run()
    if source_type == "markdown":
        return MarkdownCollector(path).run()
    return ChatGPTImporter(path).run()


@router.post("")
def ingest(payload: IngestIn, session: SessionDep, token: AuthToken) -> dict[str, Any]:
    """Run the matching collector in-process and return the result summary."""
    path = Path(payload.path).expanduser().resolve()
    if not path.is_dir():
        raise _bad_request("invalid_path", f"path must be an existing directory (got {payload.path!r})")

    started = time.monotonic()
    try:
        result = _run_collector(payload.source_type, path)
    except Exception as exc:  # noqa: BLE001 - collector already catches per-file errors
        logger.exception("ingestion run failed for %s", path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=knowledge_error_payload("ingestion_failed", f"{type(exc).__name__}: {exc}")["error"],
        ) from exc

    metrics.observe_ingestion(payload.source_type, time.monotonic() - started)
    audit(
        session,
        "ingest.run",
        payload.actor,
        "source",
        result.repo,
        {
            "source_type": payload.source_type,
            "path": str(path),
            "files_indexed": result.files_indexed,
            "documents_created": result.documents_created,
            "commits_indexed": result.commits_indexed,
            "errors": len(result.errors),
        },
    )
    session.commit()
    logger.info("ingested %s %s: %d docs in %.2fs", payload.source_type, result.repo,
                result.documents_created, result.duration)
    return {"result": result.as_dict()}
