"""Bearer-token authentication for the MKC API.

All ``/api/v1/*`` routes require ``Authorization: Bearer <token>`` where the
token matches :attr:`mkc.core.config.Settings.mkc_api_token` (env
``MKC_API_TOKEN``). ``/healthz`` and ``/metrics`` stay public so load
balancers and Prometheus can probe the service without credentials.

The comparison is a constant-time ``hmac.compare_digest`` to avoid trivial
timing side-channels.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from mkc.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _constant_time_equal(a: str, b: str) -> bool:
    """Constant-time string comparison (length is not leaked)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """FastAPI dependency enforcing the MKC bearer token.

    Returns the authenticated actor identity (the token itself doubles as the
    audit ``actor``), or raises 401 when the header is missing/malformed or
    the token does not match. The error body deliberately does not reveal
    whether the token format or the value was wrong.
    """
    expected = settings.mkc_api_token
    if not expected:
        # fail closed: misconfigured deployment must not open the API
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API token not configured"
        )
    if not authorization or not authorization.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected 'Authorization: Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided = parts[1].strip()
    if not _constant_time_equal(provided, expected):
        logger.warning("rejected API request with invalid bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return provided


#: Convenience dependency annotation for router function signatures.
AuthToken = Annotated[str, Depends(require_token)]
