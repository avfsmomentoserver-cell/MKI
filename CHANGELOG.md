# Changelog

Summary of notable changes to the Momento Knowledge Core (MKC). Full detail: [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-09-20

Milestone 1 — Foundation: the vertical slice (index a repository → search → AI context).

### Added

- **Backend core (Wave 1b):** FastAPI + SQLAlchemy + Alembic + PostgreSQL 17 under `backend/` — models for the 31 knowledge object types, the lifecycle state machine, immutable provenance, migrations, REST API, and bearer-token auth.
- **Intelligence layer (Wave 1c):** ingestion (11 git repos, markdown, git history), knowledge extraction, full-text search, contradiction detection, insight generation, the three initial reports, the AI Context API, and the `mkc` CLI (`ingest`, `search`, `health`, `status`).
- **Documentation foundation (Wave 1d):** root `README.md`, `docs/PRODUCT_BACKLOG.md`, `docs/KNOWLEDGE_MODEL.md` (canonical types/lifecycle/provenance reference), `docs/CHANGELOG.md`, and skeleton structures for `ARCHITECTURE.md`, `DEVELOPER_GUIDE.md`, `API_REFERENCE.md`, `OPS_RUNBOOK.md`, `SECURITY_MODEL.md`.
- **Environment provisioning (Wave 1a):** `ops/ENVIRONMENT.md` — verified baseline (Debian 13, PostgreSQL 17.11 + pgvector, Python 3.13, `.env` secret model, repo health table, reproduction checklist).
