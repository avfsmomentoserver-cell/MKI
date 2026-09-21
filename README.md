# MKC — Momento Knowledge Core

MKC (Momento Knowledge Core) is the knowledge-intelligence layer of the Momento Platform: the institutional memory and continuous research/planning intelligence for a crash-game and market-research ecosystem. It ingests raw artifacts — git repositories, ChatGPT conversations, markdown documents, and git history — and converts them into structured, evidence-backed knowledge objects with immutable provenance. Every object tracks where it came from, how it was extracted, and what its lifecycle state is, so the system can answer questions like *"What does Momento currently know about compression-based forecasting?"* or *"Why does the Forecast Engine work this way?"* with citations back to source files, commits, and conversations.

**Positioning:** MKC is the *authoritative knowledge registry with provenance*. The code, databases, experiments, and external sources remain sources of truth for their respective domains; MKC records what the project currently understands about them. That distinction prevents an AI-generated summary from being treated as fact and propagating its own mistakes throughout the platform.

---

## Core Principles

MKC is built on non-negotiable rules:

1. **No fabrication.** Knowledge objects are only created from ingested evidence. MKC never converts speculation into fact.
2. **No silent promotion.** Hypotheses stay hypotheses. An object only moves up the lifecycle (e.g., `hypothesis` → `validating` → `validated`) when the required evidence exists; transitions are recorded with who/what triggered them.
3. **Immutable provenance.** Every knowledge object carries an immutable provenance record: `source_type`, `source_id`, `file_path`, `commit_hash`, `author`, `date`, `extraction_method`, and an `original_text` excerpt. Provenance is never edited in place; corrections produce new objects that supersede the old ones.
4. **Failed experiments are preserved.** A failed or rejected experiment is never deleted or overwritten. It is a first-class knowledge object (`lifecycle_state = rejected` or terminal), because a negative result is evidence.
5. **Contradictions are surfaced, not resolved.** When two claims conflict, MKC records the contradiction with a severity and links both sides. It never silently picks a winner.
6. **Historical decisions are never overwritten.** Decisions can be *superseded* (with a link to the new decision), but the original rationale chain is preserved permanently.

---

## What Was Built in Milestone 1 (Wave 1)

Milestone 1 is a **vertical slice**: the full pipeline proven end-to-end on a small scope — *index a repository → search it → serve AI context*.

### Delivered in this wave

| Wave | Deliverable | Status |
|------|-------------|--------|
| 1a | Environment provisioning (`ops/ENVIRONMENT.md`: host, services, PostgreSQL, tooling) | Delivered |
| 1b | **Backend core** (`backend/`): FastAPI + SQLAlchemy + Alembic + PostgreSQL — domain models (31 object types, lifecycle states, provenance), migrations, REST API, lifecycle state machine | Delivered (parallel) |
| 1c | **Intelligence layer**: ingestion (git repos, markdown, git history), knowledge extraction, full-text search, contradiction detection, insight generation, report generation, AI Context API, `mkc` CLI | Delivered (parallel) |
| 1d | **Documentation foundation** (this directory: `README.md`, `docs/`) | Delivered |

The vertical slice covers:

- **Ingestion** of the 11 git repositories under `repos/` (source code, markdown, and git commit history), producing `document` knowledge objects with full provenance down to file path and commit hash.
- **Extraction** of structured knowledge objects — modules, engines, theories, metrics — from the ingested content.
- **Search** — full-text search over all indexed knowledge, via CLI (`mkc search "query"`) and API.
- **Context** — the AI Context API that assembles a citation-backed answer bundle for a query, ready to feed into VS Code agents, Devin, or any LLM workflow.

### Directory Layout

```
/home/admin/MKI/
├── README.md              ← this file
├── CHANGELOG.md           ← top-level changelog (summary)
├── file-master-index.json ← exhaustive file index of all repos (generated)
├── backend/               ← FastAPI + SQLAlchemy + Alembic + PostgreSQL core (Wave 1b)
│   ├── app/               ← API, models, services
│   ├── alembic/           ← database migrations
│   └── tests/             ← backend test suite
├── web/                   ← React + TypeScript dashboard (Wave 3 — not yet built)
├── docs/                  ← documentation foundation (this wave)
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   ├── CHANGELOG.md
│   ├── DEVELOPER_GUIDE.md
│   ├── KNOWLEDGE_MODEL.md
│   ├── OPS_RUNBOOK.md
│   ├── PRODUCT_BACKLOG.md
│   └── SECURITY_MODEL.md
├── ops/                   ← environment & operations (Wave 1a: ENVIRONMENT.md)
├── repos/                 ← cloned source repositories (gitignored)
│   ├── avfs-backend/
│   ├── azuredev-3867/
│   ├── InvestigationSuite/
│   ├── momento-avfs-core/
│   ├── momento-core/
│   ├── momento-core3/
│   ├── momentocore2/
│   ├── MomentoFresh/
│   ├── MomentoFX/
│   ├── MomentoRabbit/
│   └── MomentoV5/
└── content-archive/       ← chatgpt-history, papers, research content (gitignored)
```

`repos/` and `content-archive/` are gitignored: they are *inputs* to MKC, not part of the MKC codebase. The MKC database is the authoritative store; the raw files are re-ingestable.

---

## Quick Start

> Environment facts (verified on the host): Debian 13 (trixie), PostgreSQL 17 with `pgvector` and `hstore` extensions on the `mkc` database, Python 3.13, no Docker — the deployment path is venv + uvicorn + systemd. Full baseline and reproduction checklist: `ops/ENVIRONMENT.md`.

### 1. Install

```bash
cd /home/admin/MKI
python3 -m venv backend/.venv                # already created by the environment wave
./backend/.venv/bin/pip install --upgrade pip
./backend/.venv/bin/pip install -r backend/requirements.txt
```

(`backend/requirements.txt` is pinned by the backend wave; until it exists, the verified package set in `ops/ENVIRONMENT.md` §4 is the source of truth.)

### 2. Configure

```bash
cp -n .env.example .env    # then fill in real values; .env is gitignored
```

Variables (see `ops/ENVIRONMENT.md` §3): `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` (SQLAlchemy URL, psycopg3 driver), and `MKC_API_TOKEN` (40+ char bearer token for the API — generate with `openssl rand -hex 20`, never commit real values).

### 3. Migrate

```bash
cd backend
.venv/bin/alembic upgrade head
```

### 4. Run the API

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl -s http://127.0.0.1:8000/healthz
# {"status":"ok",...}
```

### 5. Ingest and Search (CLI)

```bash
mkc ingest --repos /home/admin/MKI/repos
mkc status
mkc search "forecast engine"
```

### 6. Query the API

```bash
TOKEN=$(grep '^MKC_API_TOKEN=' .env | cut -d= -f2)

curl -s -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8000/knowledge?object_type=module"

curl -s "http://127.0.0.1:8000/api/v1/status"   # unauthenticated
```

See `docs/API_REFERENCE.md` for the full endpoint list and `docs/DEVELOPER_GUIDE.md` (filled in Wave 2) for the full development workflow.

---

## What's Next

| Wave | Theme | Contents |
|------|-------|----------|
| **Wave 2** | Docs deep-dive | Fill `docs/ARCHITECTURE.md`, `docs/DEVELOPER_GUIDE.md`, `docs/API_REFERENCE.md`, `docs/SECURITY_MODEL.md`, `docs/OPS_RUNBOOK.md` from working code |
| **Wave 3** | Dashboard | React + TypeScript web UI under `web/`: Overview, Knowledge, Research, Experiments, Decisions, Insights, Planning, Search, System Health |
| **Wave 4** | QA | Test coverage targets, end-to-end pipeline test, load/soak tests, CI pipeline |
| **Wave 5** | Security | Auth hardening, rate limiting, input validation sweep, secret management, `docs/SECURITY_MODEL.md` validated against code |
| **Wave 6** | DevOps | systemd units / service supervision, backup & restore runbook, monitoring & alerting, deployment guide, `docs/OPS_RUNBOOK.md` validated |

The full product backlog, milestones, acceptance criteria, and risk register live in [`docs/PRODUCT_BACKLOG.md`](docs/PRODUCT_BACKLOG.md).

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| [`docs/PRODUCT_BACKLOG.md`](docs/PRODUCT_BACKLOG.md) | Milestones, acceptance criteria, NFRs, Definition of Done, risk register |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System overview, diagrams, per-wave design (skeleton — filled Wave 2) |
| [`docs/KNOWLEDGE_MODEL.md`](docs/KNOWLEDGE_MODEL.md) | Object types, lifecycle states, provenance fields |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | REST endpoints, auth, request/response shapes (skeleton — filled Wave 2) |
| [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) | Setup, code layout, testing, contribution workflow (skeleton — filled Wave 2) |
| [`docs/OPS_RUNBOOK.md`](docs/OPS_RUNBOOK.md) | Start/stop, backup/restore, monitoring, troubleshooting, deployment (skeleton — filled Wave 6) |
| [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) | Threat model, auth, data handling, secret policy (skeleton — filled Wave 5) |
| [`ops/ENVIRONMENT.md`](ops/ENVIRONMENT.md) | Host environment, services, versions (Wave 1a) |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Detailed changelog; see top-level `CHANGELOG.md` for the summary |
