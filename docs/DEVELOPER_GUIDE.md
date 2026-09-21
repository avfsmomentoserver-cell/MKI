# MKC Developer Guide

> **Status: skeleton (documentation foundation wave).** The section structure is final; body content is written in Wave 2 (docs deep-dive) from the working code and the environment described in `ops/ENVIRONMENT.md`.

## 1. Environment Setup

Step-by-step developer setup for a clean machine: prerequisites (Debian 13, Python 3.13, PostgreSQL 17 with the `vector` and `hstore` extensions, `git`), creating the virtualenv under `backend/.venv`, installing dependencies (the pinned `backend/requirements.txt` once the backend wave lands it; the verified package list in `ops/ENVIRONMENT.md` §4 until then), and configuring the environment from `.env.example` (copy to `.env`; the variables are `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `MKC_API_TOKEN` — generate the token with `openssl rand -hex 20`; `.env` is gitignored). Also covers the first `alembic upgrade head` and the `mkc health` smoke check that confirms a working setup.

## 2. Code Layout

Map of `backend/` — where models, schemas, routers, services, ingestion, and extraction live — plus `backend/alembic/` (migrations), `backend/tests/`, the `mkc` CLI entry point, and the repository root (`docs/`, `ops/`, gitignored `repos/` and `content-archive/`). Each directory gets a one-paragraph description of its contents and its dependencies on the others, so a newcomer can navigate without reading every file. Wave 2 generates this from the actual tree.

## 3. Development Workflow

The day-to-day loop: how to run the API in dev mode with reload (`uvicorn app.main:app --reload --port 8000`), how to run tests (`pytest` from `backend/`, test-DB conventions), lint/format tooling (`ruff` is in the pinned set) and when it runs, and how to add a migration (new Alembic revision workflow, naming, and the rule that migrations are forward-only and never edited after push). Includes the golden rule that provenance-bearing columns are immutable at the API level and the test that enforces it.

## 4. Adding a Knowledge Object Type or Lifecycle Transition

Contribution guide for the two most common core changes: adding a new object type (model, enum, schema, migration, extraction classifier, docs in `KNOWLEDGE_MODEL.md`) and adding a lifecycle transition (state machine update, transition audit logging, tests for allowed and rejected transitions). Each change requires an updated changelog entry — see `docs/CHANGELOG.md` for the format.

## 5. Testing Guide

Test architecture: unit tests (models, state machine, extraction rules), integration tests (API endpoints against a test database), and the end-to-end pipeline test that runs a mini ingest → extract → search → context flow. Covers fixtures (sample repo, sample commit, seeded knowledge objects), how to add a regression test for a found defect, and the coverage expectations from the product backlog NFRs (≥ 70% on the app package, target ≥ 85% in Wave 4). No test may be skipped without a recorded reason in the test file.

## 6. CLI Development

How the `mkc` CLI is structured (command registration, shared `.env`/config loading, exit codes) and how to add a command: implement the service call, add a subparser with `--help` text, add a failing-exit test. Documents the contract that CLI errors are human-readable and non-zero on failure (a Milestone 1 acceptance criterion) and that the four base commands are `mkc ingest`, `mkc search "query"`, `mkc health`, and `mkc status`.

## 7. Conventions

The house rules: naming (snake_case modules, PascalCase models/schemas, enum values exactly as in `KNOWLEDGE_MODEL.md`), comment policy (why, not what), error handling (typed errors, no swallowed exceptions, no stringly-typed failure), logging (structured JSON, no secrets in log lines — token and password fields are redacted), and the no-fabrication rule applied to code: extraction code must emit a citation (`original_text` + `file_path` + `commit_hash`) or not emit the object at all.
