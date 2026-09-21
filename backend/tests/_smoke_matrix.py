"""Smoke matrix for the newly mounted routers (search, reports, ingest, context).

Run: ``./.venv/bin/python tests/_smoke_matrix.py`` — not collected by pytest
(filename does not start with ``test_``). Runs against ``mkc_test`` only
(env fixed before mkc caches settings); seeds a small registry and cleans it
up afterwards.
"""

from __future__ import annotations

import os
import uuid

_TEST_DB_URL = os.environ.get("MKC_TEST_DB_URL", "postgresql+psycopg://mkc:mkc@localhost:5432/mkc_test")
assert "mkc_test" in _TEST_DB_URL
os.environ["MKC_DATABASE_URL"] = _TEST_DB_URL
os.environ["MKC_API_TOKEN"] = "mkc-test-token-0123456789abcdef"

import mkc.core.config as config_mod  # noqa: E402
import mkc.core.database as database_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mkc.api.app import create_app  # noqa: E402

config_mod.reset_settings()
database_mod.reset_engine()

TOKEN = "mkc-test-token-0123456789abcdef"
H = {"Authorization": f"Bearer {TOKEN}"}

MARKER = uuid.uuid4().hex[:10]
app = create_app()

with TestClient(app) as client:
    # seed two knowledge objects for the smoke topic
    seed_ids = []
    for state in ("validated", "idea"):
        r = client.post(
            "/api/v1/knowledge",
            headers=H,
        json={
            "type": "hypothesis",
            "title": f"smoke-{MARKER}-topic-{state}",
            "lifecycle_state": state,
            "content_summary": f"smoke-{MARKER} summary line",
            "body": f"smoke-{MARKER} body text",
            "provenance": {
                    "source_type": "markdown",
                    "source_id": "smoke",
                    "source_location": "smoke.md#x",
                    "original_text": "smoke pack object body text",
                    "extraction_method": "manual",
                },
            },
        )
        assert r.status_code == 201, r.text
        seed_ids.append(r.json()["object"]["id"])

    lines: list[str] = []

    def probe(label: str, method: str, path: str, **kw) -> None:
        headers = kw.pop("headers", None)
        resp = client.request(method, path, headers=headers, **kw)
        try:
            body = resp.json()
            text = str(body)
        except Exception:
            text = resp.text
        if len(text) > 320:
            text = text[:320] + f"... <{len(text)} chars>"
        lines.append(f"[{resp.status_code}] {label}: {method} {path} -> {text}")

    # --- search ---
    probe("search no-token", "POST", "/api/v1/search", json={"query": f"smoke-{MARKER}"})
    probe("search token", "POST", "/api/v1/search", headers=H, json={"query": f"smoke-{MARKER}"})
    probe("search empty-query", "POST", "/api/v1/search", headers=H, json={"query": "   "})
    probe(
        "search filter-no-match",
        "POST",
        "/api/v1/search",
        headers=H,
        json={"query": f"smoke-{MARKER}", "types": ["decision"]},
    )

    # --- reports ---
    probe("reports list no-token", "GET", "/api/v1/reports")
    probe("reports list token", "GET", "/api/v1/reports", headers=H)
    probe("reports unknown-uuid", "GET", f"/api/v1/reports/{uuid.uuid4()}", headers=H)
    probe(
        "reports generate unknown-type",
        "POST",
        "/api/v1/reports/generate",
        headers=H,
        json={"report_type": "bogus-type"},
    )

    # --- ingest ---
    probe("ingest no-token", "POST", "/api/v1/ingest", json={"source_type": "git", "path": "/tmp"})
    probe(
        "ingest bad-path",
        "POST",
        "/api/v1/ingest",
        headers=H,
        json={"source_type": "git", "path": "/nonexistent-dir-smoke"},
    )

    # --- context ---
    probe("context no-token", "GET", f"/api/v1/context/smoke-{MARKER}")
    probe("context architecture no-token", "GET", "/api/v1/context/architecture")
    probe("context topic token", "GET", f"/api/v1/context/smoke-{MARKER}", headers=H)
    probe("context architecture token", "GET", "/api/v1/context/architecture", headers=H)
    probe("context query no-token", "POST", "/api/v1/context/query", json={"query": f"smoke-{MARKER}"})
    probe(
        "context query token",
        "POST",
        "/api/v1/context/query",
        headers=H,
        json={"query": f"smoke-{MARKER}", "top_k": 5},
    )
    probe("context empty-topic", "GET", "/api/v1/context/", headers=H)
    probe("context unknown-topic", "GET", f"/api/v1/context/no-such-topic-{MARKER}", headers=H)

    # cleanup seed rows
    session = database_mod.get_session_factory()()
    try:
        from sqlalchemy import delete

        from mkc.models import KnowledgeObject

        session.execute(delete(KnowledgeObject).where(KnowledgeObject.id.in_([uuid.UUID(i) for i in seed_ids])))
        session.commit()
    finally:
        session.close()

    print("\n".join(lines))
