# MKC Architecture

> **Status: skeleton (documentation foundation wave).** The section structure is final; body content is written in Wave 2 (docs deep-dive) by the Architect, filled in from the working backend code. Each section below previews its scope so the authoring wave knows exactly what to fill in.

## 1. System Overview

Describes MKC as the knowledge-intelligence layer of the Momento Platform: what it is (authoritative knowledge registry with provenance), what it is not (not a source of truth for code, data, or experiments — it records what the project currently *understands* about them), and the end-to-end pipeline at a glance: `collect → understand → research → validate → record → implement → observe → update knowledge → plan next work`. The filled-in section will list the six named capabilities (ingestion, knowledge extraction, research management, insight generation, planning, AI context) and map each to the component that implements it.

## 2. Architecture Diagram (text)

An ASCII diagram of the full pipeline, from sources to consumers:

```
repos/ (git)          content-archive/ (chatgpt-history, papers, notes)
      └──────────────────────┬──────────────────────────┘
                             ▼
                       Ingestion (file walkers, commit-hash keys)
                             ▼
                  Extraction → Knowledge store (PostgreSQL 17)
                     │        · full-text (tsvector/GIN)
                     │        · vector (pgvector 0.8.0)
                     ▼
        Intelligence services (contradiction, insight, report, context)
                             ▼
              API (FastAPI) · CLI (mkc) · Dashboard (Wave 3)
                             ▼
                     AI agents / engineers
```

The filled-in section will add per-component detail: which Python modules implement each stage, the database tables each stage reads/writes, and the exact data flow for a search request and an ingest run.

## 3. Backend Core (Wave 1b deliverable)

Design of the FastAPI + SQLAlchemy + Alembic + PostgreSQL core: application layout under `backend/` (models, schemas, routers, services, ingestion, extraction, CLI entry point), the ORM model inventory, the Alembic migration policy, and the lifecycle state machine (allowed transitions, who may trigger them, transition audit trail). Will document the 31 object types, the 15 lifecycle states (10 active + 4 terminal + `unknown` catch-all), and the immutability of provenance columns. The stack is fixed: Python 3.13, FastAPI 0.141.1, SQLAlchemy 2.0.54, psycopg 3.3.6, Alembic 1.20.0, PostgreSQL 17.11 with `vector` 0.8.0 (versions verified in `ops/ENVIRONMENT.md` §4).

## 4. Intelligence Layer (Wave 1c deliverable)

Design of the pipeline that turns raw artifacts into knowledge: file walkers and the binary-skip policy (InvestigationSuite and momento-avfs-core contain 15 MB+ zips and large blobs), commit-hash-keyed idempotency, the extraction rules that produce entities (modules, engines, theories, metrics) and classify object types, full-text search (tsvector) and hybrid search (pgvector), contradiction detection (claim_a vs claim_b, severity high/medium/low), insight generation (pattern/trend/gap/contradiction/recommendation), the three report writers (project-knowledge, research-gaps, implementation-plan), and the AI Context API assembly (ranked objects + citations, token-budgeted). Will document the pipeline stage-by-stage with the module path that implements each stage.

## 5. Dashboard (Wave 3)

Placeholder for the React + TypeScript dashboard architecture under `web/`: build tooling, the nine views (Overview, Knowledge, Research, Experiments, Decisions, Insights, Planning, Search, System Health), the API client design, bearer-token handling in the browser, and static-serving deployment on the same host. To be authored when `web/` exists (Wave 3); this section will state the API contract assumptions the dashboard relies on, including the unauthenticated ops surface it may poll without a token.

## 6. Data Model

Complete relational schema: all tables and columns (knowledge objects, provenance, entity_relations, research, decisions, experiments, insights, contradictions, ingest runs, report history), indexes and their rationale (full-text GIN, vector, foreign keys), the enum definitions (object types, lifecycle states, relation types, insight types), and cardinality rules. Will include the ER diagram and cross-reference `KNOWLEDGE_MODEL.md` for the semantic meaning of each enum value, keeping `KNOWLEDGE_MODEL.md` as the single source for enum values and this section as the source for column types, constraints, and indexes.

## 7. Security Model

Summary of the trust model and what the API protects: bearer-token authentication (`MKC_API_TOKEN`), which endpoints are unauthenticated by default (`/healthz`, `/metrics`, `/api/v1/status`), the no-secrets-in-code policy, input validation behavior (Pydantic 2 schemas, 422 on invalid enums), rate limiting, and how ingest sources (untrusted repo content) are treated as data, never as code. The authoritative, threat-model-level document is `SECURITY_MODEL.md` (filled in Wave 5); this section will link to it and restate only the architecture-relevant constraints (e.g., where the token is verified in the request path, how `.env` is kept out of git and logs).

## 8. Deployment (Wave 6)

How MKC runs on the Debian host in production. Docker is **not available** on this host (verified in `ops/ENVIRONMENT.md` §6), so the deployment path is: systemd unit for the uvicorn API (systemd is present and running), a systemd timer for scheduled ingest, PostgreSQL 17 managed by the distro service, and the dashboard static build served on the same host. This section will document the unit files, environment-variable wiring (`.env` loaded outside the unit or via `EnvironmentFile`), the no-docker rationale, and the monitoring setup (metrics endpoint + scrape target), authored together with `OPS_RUNBOOK.md` in Wave 6.
