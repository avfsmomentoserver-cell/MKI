"""FastAPI application factory for the MKC API.

Public (unauthenticated):

- ``GET /healthz``: liveness + database probe.
- ``GET /metrics``: Prometheus text-format counters/gauges.

Authenticated (``Authorization: Bearer <MKC_API_TOKEN>``):

- ``/api/v1/*``: knowledge CRUD, research items, decisions, experiments,
  status summary, search, reports, ingestion, AI context.

The factory is dependency-overridable for tests: ``create_app()`` builds a
fresh app whose DB session dependency can be swapped via
``app.dependency_overrides[get_session]``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mkc import __version__
from mkc.api.metrics import metrics
from mkc.api.routers import context, decisions, experiments, ingest, knowledge, reports, research, search
from mkc.core.auth import require_token
from mkc.core.database import get_engine, get_session, get_session_factory

logger = logging.getLogger("mkc.api")


async def _db_probe() -> str:
    """Ping the database and return 'connected' or 'disconnected'."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return "connected"
    except Exception:  # noqa: BLE001 - any DB error means 'disconnected'
        logger.debug("healthz database probe failed", exc_info=True)
        return "disconnected"


def create_app() -> FastAPI:
    """Build the MKC FastAPI application.

    Importing :mod:`mkc.models` here registers every table on
    ``Base.metadata`` (needed by Alembic env and health probes alike).
    """
    import mkc.models  # noqa: F401

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        # Startup: warn loudly (but not fatally) if the DB is unreachable so
        # operators see the issue in logs immediately.
        db_state = await _db_probe()
        if db_state == "disconnected":
            logger.error("MKC API started but the database is UNREACHABLE; check MKC_DATABASE_URL")
        else:
            logger.info("MKC API started, database connected")
        yield

    app = FastAPI(
        title="MKC API",
        version=__version__,
        description="Momento Knowledge Core: provenance-first knowledge registry.",
        lifespan=lifespan,
    )

    # -- public routes -----------------------------------------------------
    @app.get("/healthz", tags=["public"])
    async def healthz() -> JSONResponse:
        """Liveness + database probe (public)."""
        db_state = await _db_probe()
        payload = {
            "status": "ok" if db_state == "connected" else "degraded",
            "database": db_state,
            "version": __version__,
        }
        return JSONResponse(payload)

    @app.get("/metrics", response_class=Response, tags=["public"])
    async def metrics_endpoint() -> Response:
        """Prometheus text-format metrics (public)."""
        db_state = await _db_probe()
        knowledge_count = 0
        document_count = 0
        if db_state == "connected":
            from mkc.models import Document, KnowledgeObject

            session = get_session_factory()()
            try:
                knowledge_count = session.scalar(select(func.count()).select_from(KnowledgeObject)) or 0
                document_count = session.scalar(select(func.count()).select_from(Document)) or 0
            finally:
                session.close()
        body = metrics.render(knowledge_count or 0, document_count or 0)
        return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")

    # -- status (authenticated) -------------------------------------------
    @app.get("/api/v1/status", dependencies=[Depends(require_token)], tags=["status"])
    async def status_summary(session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
        """Registry summary: counts by type, lifecycle distribution, recent activity."""
        from mkc.models import AuditLog, KnowledgeObject

        by_type = dict(
            session.execute(select(KnowledgeObject.type, func.count()).group_by(KnowledgeObject.type)).all()
        )
        by_state = dict(
            session.execute(
                select(KnowledgeObject.lifecycle_state, func.count()).group_by(
                    KnowledgeObject.lifecycle_state
                )
            ).all()
        )
        total = session.scalar(select(func.count()).select_from(KnowledgeObject)) or 0
        recent = session.execute(select(AuditLog).order_by(AuditLog.at.desc()).limit(20)).scalars().all()
        return {
            "version": __version__,
            "knowledge_objects_total": total,
            "by_type": by_type,
            "by_lifecycle_state": by_state,
            "recent_activity": [entry.to_dict() for entry in recent],
        }

    # -- routers -----------------------------------------------------------
    app.include_router(knowledge.router)
    app.include_router(research.router)
    app.include_router(decisions.router)
    app.include_router(experiments.router)
    app.include_router(search.router)
    app.include_router(reports.router)
    app.include_router(ingest.router)
    app.include_router(context.router)

    # -- error handlers (no stack traces ever reach clients) ---------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Log server-side, return a generic 500 (never leak internals)."""
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"error": {"code": "internal_error", "detail": "internal server error"}}
        )

    return app
