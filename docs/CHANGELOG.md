# Changelog

All notable changes to the Momento Knowledge Core are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for the API surface. The top-level `CHANGELOG.md` in the repository root is a summary of this file.

## [0.1.0] - 2026-09-20

Milestone 1 — Foundation: the vertical slice (index a repository → search → context) with the full backend core, intelligence layer, documentation foundation, and environment provisioning.

### Added

- **Backend core (Wave 1b):** FastAPI + SQLAlchemy + Alembic + PostgreSQL 17 application under `backend/` — domain models for the 31 knowledge object types, the 15 lifecycle states (10 active + 4 terminal + `unknown` catch-all) with the enforced transition state machine, immutable provenance fields, Alembic migrations, the REST API (knowledge, research, decisions, experiments, ops surface), and the bearer-token authentication model (`MKC_API_TOKEN`).
- **Intelligence layer (Wave 1c):** ingestion of the 11 git repositories under `repos/` (files, markdown, git history/commits) with commit-hash-keyed idempotency; structured knowledge extraction (modules, engines, theories, metrics) with mandatory citation; full-text search (CLI + API); contradiction detection with severity tiers (recorded, never auto-resolved); insight generation (pattern, trend, gap, contradiction, recommendation); the three initial reports (`project-knowledge-YYYY-MM-DD.md`, `research-gaps-YYYY-MM-DD.md`, `implementation-plan-YYYY-MM-DD.md`); the AI Context API; and the `mkc` CLI (`mkc ingest`, `mkc search "query"`, `mkc health`, `mkc status`).
- **Documentation foundation (Wave 1d):** root `README.md` (overview, core principles, quick start, what's next, documentation map); `docs/PRODUCT_BACKLOG.md` (milestones 1–3 with acceptance criteria, non-functional requirements, per-milestone Definition of Done, risk register); `docs/KNOWLEDGE_MODEL.md` (object types, lifecycle states, provenance — the canonical enum reference); `docs/CHANGELOG.md` (this file); top-level `CHANGELOG.md`; and skeleton structures with section previews for `docs/ARCHITECTURE.md`, `docs/DEVELOPER_GUIDE.md`, `docs/API_REFERENCE.md` (real endpoint inventory), `docs/OPS_RUNBOOK.md`, and `docs/SECURITY_MODEL.md` to be filled from working code in Waves 2/5/6.
- **Environment provisioning (Wave 1a):** `ops/ENVIRONMENT.md` — verified baseline for Debian 13 (trixie): PostgreSQL 17.11 with `pgvector` (vector 0.8.0) and `hstore` extensions, the `mkc` role/database, Python 3.13 venv at `backend/.venv` with the pinned dependency set, `.env`/`.env.example` with the `MKC_API_TOKEN` secret model, the 11-repo health table under `repos/`, and the reproduction checklist. Docker confirmed absent; the deployment path is venv + uvicorn + systemd.
- **Workspace snapshot:** `.gitignore` (excluding `repos/`, `content-archive/`, `*.db`, `.env`, venvs, logs) and `file-master-index.json` (exhaustive file index of all repos, ~385 KB).
