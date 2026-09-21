"""Thin compatibility shim over the backend core's model names.

The intelligence layer codes against the core package (``mkc.models``).
If a model or column name differs slightly from the documented contract
this module provides a single adaptation point; it never redefines
tables or schemas.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("mkc.db_compat")


class CoreUnavailable(Exception):
    """Raised when the backend core package is not importable."""


def core_models() -> Any:
    """Import the core model namespace, or raise :class:`CoreUnavailable`."""
    try:
        import mkc.models as models  # type: ignore[attr-defined]
        return models
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all
        raise CoreUnavailable(
            f"backend core (mkc.models) not importable: {type(exc).__name__}: {exc}"
        ) from exc


def get_model(kind: str) -> Any:
    """Return the core model class for *kind* (``"Source"`` etc.).

    Falls back to a case-insensitive lookup when the exact name is absent
    (e.g. ``knowledge_object`` vs ``KnowledgeObject``).
    """
    models = core_models()
    model = getattr(models, kind, None)
    if model is not None:
        return model
    wanted = kind.lower()
    for name in dir(models):
        if name.lower() == wanted and isinstance(getattr(models, name), type):
            logger.debug("db_compat: mapped %r -> %s", kind, name)
            return getattr(models, name)
    raise AttributeError(f"core model {kind!r} not found in mkc.models")


def model_query(model: Any) -> Any:
    """Columnless ``SELECT * FROM <model>`` for the installed SQLAlchemy.

    Class-level ``Model.select()`` (1.4 legacy) was removed in SQLAlchemy
    2.0, so build the statement with :func:`sqlalchemy.select` instead.
    """
    from sqlalchemy import select

    return select(model)


def has_column(model: Any, column: str) -> bool:
    """True when *model* declares *column* (used for optional fields)."""
    mapper = getattr(model, "__mapper__", None)
    if mapper is None:
        return hasattr(model, column)
    return column in mapper.column_attrs


def column_value(row: Any, column: str, default: Any = None) -> Any:
    """Read an optional column without raising when the core lacks it."""
    value = getattr(row, column, None)
    return default if value is None else value
