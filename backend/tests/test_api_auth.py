"""Auth boundary tests: public endpoints need no token, /api/v1 needs the right one.

Contract (src/mkc/api/app.py + src/mkc/core/auth.py):

- ``GET /healthz`` and ``GET /metrics`` are public (load balancer /
  Prometheus probes) and return 200 with NO Authorization header.
- ``GET /api/v1/status`` requires ``Authorization: Bearer <MKC_API_TOKEN>``:
  401 with no header, 401 with a wrong token, 200 with the test token.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import conftest
import mkc.core.config as config_mod
import mkc.core.database as database_mod
from mkc.api.app import create_app

TEST_TOKEN = conftest.TEST_TOKEN


def test_healthz_is_public_without_token(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "connected"
    assert body["status"] == "ok"
    assert body["version"]


def test_metrics_is_public_without_token(client) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "mkc_knowledge_objects" in body
    assert "mkc_documents_total" in body
    assert "mkc_uptime_seconds" in body


def test_status_without_token_is_401(client) -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_status_with_wrong_token_is_401(client) -> None:
    response = client.get("/api/v1/status", headers={"Authorization": "Bearer not-the-right-token"})
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_status_with_wrong_scheme_is_401(client) -> None:
    # The scheme must be "bearer" (case-insensitive); anything else is rejected.
    response = client.get("/api/v1/status", headers={"Authorization": f"Basic {TEST_TOKEN}"})
    assert response.status_code == 401


def test_status_with_token_but_no_bearer_prefix_is_401(client) -> None:
    response = client.get("/api/v1/status", headers={"Authorization": TEST_TOKEN})
    assert response.status_code == 401


def test_status_with_correct_token_is_200(client, auth_headers) -> None:
    response = client.get("/api/v1/status", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_objects_total"] >= 0
    assert isinstance(body["by_type"], dict)
    assert isinstance(body["by_lifecycle_state"], dict)
    assert isinstance(body["recent_activity"], list)


def test_bearer_scheme_is_case_insensitive_and_whitespace_tolerant(client) -> None:
    headers = {"Authorization": f"bearer   {TEST_TOKEN} "}
    assert client.get("/api/v1/status", headers=headers).status_code == 200


def test_auth_boundary_holds_on_a_second_fresh_app_instance() -> None:
    """Independence from the shared ``client`` fixture: a fresh app behaves the same."""
    config_mod.reset_settings()
    database_mod.reset_engine()
    app = create_app()
    with TestClient(app) as fresh:
        assert fresh.get("/healthz").status_code == 200
        assert fresh.get("/metrics").status_code == 200
        token_headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        assert fresh.get("/api/v1/status").status_code == 401
        assert fresh.get("/api/v1/status", headers=token_headers).status_code == 200
