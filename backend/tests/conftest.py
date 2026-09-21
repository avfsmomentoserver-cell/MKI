"""Shared fixtures for the MKC backend test suite.

Determinism strategy:

- The environment is fixed *before* ``mkc.core.config`` caches settings:
  every test runs against the ``mkc_test`` database (never the production
  ``mkc`` db) with a fixed bearer token, so auth behaviour is reproducible.
- ``mkc`` keeps process-wide caches (settings, engine, session factory);
  they are reset at session start, so the first test gets a clean engine
  bound to the test DB.
- Tests clean up after themselves: API-level fixtures delete the rows they
  create, and collector tests exercise the read-only ``collect()`` path.

The test database URL is overridable via ``MKC_TEST_DB_URL``; it defaults to
``mkc_test`` on localhost.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "mkc-test-token-0123456789abcdef"

_TEST_DB_URL = os.environ.get("MKC_TEST_DB_URL", "postgresql+psycopg://mkc:mkc@localhost:5432/mkc_test")

os.environ["MKC_DATABASE_URL"] = _TEST_DB_URL
os.environ["MKC_API_TOKEN"] = TEST_TOKEN
os.environ.setdefault("MKC_ENV", "dev")

# Safety guard: this suite must never touch the production database.
assert "mkc_test" in _TEST_DB_URL, f"refusing to run tests against non-test DB: {_TEST_DB_URL}"

import mkc.core.config as config_mod  # noqa: E402
import mkc.core.database as database_mod  # noqa: E402
from mkc.api.app import create_app  # noqa: E402


def _git(repo: Path, *args: str, author: str = "QA Bot", email: str = "qa-bot@mkc.test") -> None:
    """Run a git command in *repo* with deterministic author/committer identity."""
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            f"user.name={author}",
            "-c",
            f"user.email={email}",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _reset_process_state() -> Iterator[None]:
    """Drop cached settings/engine once per session so the first test sees our env."""
    config_mod.reset_settings()
    database_mod.reset_engine()
    yield
    database_mod.reset_engine()
    config_mod.reset_settings()


@pytest.fixture
def app():
    """A fresh FastAPI app bound to the test DB and the fixed test token."""
    config_mod.reset_settings()
    database_mod.reset_engine()
    return create_app()


@pytest.fixture
def client(app) -> TestClient:
    """Authenticated TestClient (bearer token + DB-lifespan probe executed)."""
    config_mod.reset_settings()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Authorization header carrying the test token."""
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def test_db():
    """Zero-arg factory returning a live session on the test DB (closed by caller)."""
    config_mod.reset_settings()
    database_mod.reset_engine()

    def factory():
        return database_mod.get_session_factory()()

    return factory


@pytest.fixture
def seed_knowledge(client, auth_headers):
    """Create a knowledge object via the API; auto-deletes it after the test."""
    created: list[str] = []

    def create(
        type: str = "hypothesis",
        title: str | None = None,
        lifecycle_state: str = "unknown",
        provenance: dict | None = None,
    ) -> dict:
        payload = {
            "type": type,
            "title": title or f"seed-{uuid.uuid4().hex[:8]}",
            "lifecycle_state": lifecycle_state,
            "provenance": provenance or {"source_location": "tests/conftest.py#seed"},
        }
        response = client.post("/api/v1/knowledge", headers=auth_headers, json=payload)
        assert response.status_code == 201, response.text
        created.append(response.json()["object"]["id"])
        return response.json()["object"]

    yield create

    for obj_id in created:
        session = database_mod.get_session_factory()()
        try:
            from sqlalchemy import delete

            from mkc.models import KnowledgeObject

            session.execute(delete(KnowledgeObject).where(KnowledgeObject.id == uuid.UUID(obj_id)))
            session.commit()
        finally:
            session.close()


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A scratch git repository for collector tests.

    Layout:
    - 3 source files committed across 2 commits (engine.py, README.md, config.json);
    - 1 binary ``asset.png`` (skipped by collectors);
    - a ``node_modules/`` tree with a tracked file (SKIP_DIRECTORIES);
    - one tracked symlink ``link_outside.txt`` pointing to a file OUTSIDE the
      repo (the T-N1 symlink-escape probe from docs/THREAT_MODEL.md).
    """
    repo = tmp_path / "collector-repo"
    repo.mkdir()
    outside_target = tmp_path / "outside-secret.txt"
    outside_target.write_text("MKC-API-TOKEN=do-not-ingest-this\n", encoding="utf-8")

    _git(repo, "init", "-q", "-b", "main")

    (repo / "engine.py").write_text(
        "class ForecastEngine:\n    def run(self):\n        return 1\n", encoding="utf-8"
    )
    (repo / "README.md").write_text("# Collector Engine\n\nWe decided to use the engine.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial: engine + readme")

    (repo / "config.json").write_text('{"mode": "test"}', encoding="utf-8")
    (repo / "asset.png").write_bytes(
        bytes.fromhex("89504e470d0a1a0a0000000d494844520000000000000000000001")
    )
    node_modules = repo / "node_modules" / "junk"
    node_modules.mkdir(parents=True)
    (node_modules / "junk.js").write_text("var x = 1;", encoding="utf-8")
    # T-N1 probe: a tracked symlink whose target lives OUTSIDE the repository.
    (repo / "link_outside.txt").symlink_to(outside_target)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add config, asset, node_modules, outside symlink")

    return repo
