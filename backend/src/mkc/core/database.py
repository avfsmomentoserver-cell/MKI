"""Database engine, session factory, and declarative base for MKC.

All models live in :mod:`mkc.models` and register their tables on
``Base.metadata``. Importing that module (which the API app factory and the
Alembic environment do) makes ``Base.metadata`` complete.

Engine and session factory are created lazily from settings, so importing
this module never requires the environment to be configured.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mkc.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """Declarative base for all MKC tables (snake_case ``__tablename__`` convention)."""


class SessionLocal:
    """Familiar ``SessionLocal()`` factory, bound lazily to the settings URL.

    ``SessionLocal()`` returns a real :class:`~sqlalchemy.orm.Session`; the
    underlying sessionmaker (and engine) is created on first use so imports
    stay side-effect free.
    """

    def __new__(cls) -> Session:
        return get_session_factory()()


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine, creating it on first use.

    The URL comes from :class:`~mkc.core.config.Settings` (never hardcoded).
    """
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.mkc_database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=10,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, creating it on first use."""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one DB session per request, always closed.

    Commits are the caller's job (routers commit explicitly); this generator
    only guarantees the session is closed even on errors.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables if they do not exist (development convenience).

    Production schema is managed by Alembic; this helper is for local
    bootstrap and for tests that target a database Alembic already migrated.
    """
    import mkc.models  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(get_engine())


def reset_engine() -> None:
    """Dispose of the cached engine/session factory (used by tests)."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
