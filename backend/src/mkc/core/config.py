"""MKC runtime configuration.

Settings are resolved from environment variables, with the repo-root ``.env``
file auto-loaded as a fallback. Variable names are prefixed ``MKC_`` and
mapped case-insensitively onto the field names of :class:`Settings`.

Nothing is hardcoded: the database URL, API token, environment and log level
all come from the environment, so the same code runs in dev, staging and prod.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

#: Repo root = the MKI workspace root (this file is MKI/backend/src/mkc/core/config.py).
REPO_ROOT: Path = Path(__file__).resolve().parents[4]

#: Location of the canonical .env file loaded by Settings (repo root).
ENV_FILE_PATH: Path = REPO_ROOT / ".env"

#: Sentinel meaning "token intentionally unset; auth must reject everything".
_UNSET_TOKEN = "__unset__"


class Settings(BaseSettings):
    """Validated MKC settings.

    Environment variables (all optional unless noted):

    - ``MKC_DATABASE_URL``: SQLAlchemy 2.0 URL for Postgres
      (e.g. ``postgres://mkc:mkc@localhost:5432/mkc``). Falls back to the
      generic ``DATABASE_URL`` variable when ``MKC_DATABASE_URL`` is unset,
      so the shared repo-root .env (env wave) works as-is.
    - ``MKC_API_TOKEN``: bearer token required for all ``/api/v1/*`` routes.
      If unset, :func:`load_settings` fails closed: the token stays a random
      per-process value so no request can ever match, and a warning is logged.
    - ``MKC_ENV``: deployment environment (dev|staging|prod), default dev.
    - ``MKC_LOG_LEVEL``: root log level name, default INFO.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    mkc_database_url: str = Field(default="")
    mkc_api_token: str = Field(default=_UNSET_TOKEN)
    mkc_env: Literal["dev", "staging", "prod"] = Field(default="dev")
    mkc_log_level: str = Field(default="INFO")
    mkc_api_base_url: str = Field(default="http://127.0.0.1:8000")

    @property
    def token_is_configured(self) -> bool:
        """True when a real API token is present (not the unset sentinel)."""
        return bool(self.mkc_api_token) and self.mkc_api_token != _UNSET_TOKEN


def _load_dotenv_overlays() -> dict[str, str]:
    """Parse .env files into a value mapping (first file wins per variable).

    The repo-root .env is authoritative; an optional backend-local .env may
    supply overrides during local development. Values from the OS environment
    always take priority over file values.
    """
    paths = [REPO_ROOT / "backend" / ".env", ENV_FILE_PATH]
    values: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.debug("skipping unreadable env file %s", path)
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values.setdefault(key, value)
    return values


def _build_values() -> dict[str, object]:
    """Merge OS environment over .env files for each settings field."""
    values: dict[str, object] = {}
    file_values = _load_dotenv_overlays()
    for field_name in Settings.model_fields:
        env_value = os.environ.get(field_name.upper())
        if env_value is not None:
            values[field_name] = env_value
        elif field_name.upper() in file_values:
            values[field_name] = file_values[field_name.upper()]
    return values


def load_settings() -> Settings:
    """Load and validate settings; fail fast with actionable errors.

    Returns a populated :class:`Settings`. Raises ``RuntimeError`` when
    ``MKC_DATABASE_URL`` is missing entirely, or when ``MKC_LOG_LEVEL`` is not
    a recognized level. A missing ``MKC_API_TOKEN`` does not raise: a random
    per-process token is substituted (so the API rejects every request —
    fail closed) and a warning is logged.
    """
    settings = Settings(**_build_values())

    if not settings.mkc_database_url:
        # compat: the shared .env (env wave) publishes DATABASE_URL
        fallback = os.environ.get("DATABASE_URL") or _load_dotenv_overlays().get("DATABASE_URL")
        if fallback:
            settings.mkc_database_url = fallback  # type: ignore[misc]

    if not settings.mkc_database_url:
        raise RuntimeError(
            "MKC_DATABASE_URL is not set. "
            f"Set it in the environment or in {ENV_FILE_PATH} "
            "(expected form: postgres://mkc:mkc@localhost:5432/mkc)."
        )

    level = settings.mkc_log_level.upper()
    if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        raise RuntimeError(
            f"MKC_LOG_LEVEL must be one of CRITICAL/ERROR/WARNING/INFO/DEBUG, got {settings.mkc_log_level!r}."
        )
    settings.mkc_log_level = level  # type: ignore[misc]

    if not settings.token_is_configured:
        logger.warning(
            "MKC_API_TOKEN is not set: all /api/v1 requests will be rejected (fail closed). "
            "Set MKC_API_TOKEN in the environment or %s.",
            ENV_FILE_PATH,
        )
        settings.mkc_api_token = secrets.token_urlsafe(32)  # type: ignore[misc]

    return settings


_CACHED_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Process-level settings accessor (FastAPI dependency).

    Returns the cached settings, loading them on first use. Tests call
    :func:`reset_settings` between environments.
    """
    global _CACHED_SETTINGS  # noqa: PLW0603
    if _CACHED_SETTINGS is None:
        _CACHED_SETTINGS = load_settings()
    return _CACHED_SETTINGS


def reset_settings() -> None:
    """Clear the process-level cache (used by tests that swap environments)."""
    global _CACHED_SETTINGS  # noqa: PLW0603
    _CACHED_SETTINGS = None


def bootstrap() -> Settings:
    """Entry-point bootstrap for the CLI: load settings and apply the log level.

    Returns the process settings so callers can access them. Raises
    ``RuntimeError`` with an actionable message when configuration is
    invalid (missing DB URL / bad log level) — the CLI prints it and exits
    non-zero.
    """
    settings = get_settings()
    logging.basicConfig(level=settings.mkc_log_level)
    logger.debug("settings bootstrapped: env=%s log_level=%s", settings.mkc_env, settings.mkc_log_level)
    return settings
