"""Alembic environment: wired to ``mkc.core.database.Base.metadata``.

The database URL is resolved from ``mkc.core.config`` (env / repo .env),
never hardcoded. ``target_metadata`` comes from the declarative base, so
``alembic revision --autogenerate`` diffs against the models in
``mkc.models``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importing mkc.models registers every table on Base.metadata.
import mkc.models  # noqa: F401
from mkc.core.config import get_settings
from mkc.core.database import Base

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:  # noqa: BLE001 - allow running without a logging config
        pass

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the DB URL from settings (works whether env or .env is set)."""
    settings = get_settings()
    url = settings.mkc_database_url
    if not url:
        raise RuntimeError("MKC_DATABASE_URL (or DATABASE_URL) must be set for Alembic migrations.")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to the database)."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
