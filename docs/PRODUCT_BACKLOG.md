# MKC Product Backlog

Milestone-level backlog for the Momento Knowledge Core (MKC). Each milestone lists its work items with concrete acceptance criteria. The Definition of Done for a milestone is in §NFRs / DoD, and the Risk Register is at the end.

**Governing principle:** MKC is an *authoritative knowledge registry with provenance* — never a source of truth in itself. Nothing in this backlog may ship a feature that fabricates knowledge, silently promotes a hypothesis to validated, or destroys provenance.

---

## Milestone 1 (NOW): Foundation

**Goal:** prove the vertical slice end-to-end — *index a repository → search it → serve citation-backed AI context* — with the backend core, the intelligence layer, and the documentation foundation all in place.

### 1.1 Ingestion

- **1.1.1** Ingest all git repositories under `/home/admin/MKI/repos` (11 repos: `avfs-backend`, `azuredev-3867`, `InvestigationSuite`, `momento-avfs-core`, `momento-core`, `momentocore2`, `MomentoFresh`, `MomentoFX`, `MomentoRabbit`, `MomentoV5`, and any additional repos present in the directory at ingest time).
- **1.1.2** Ingest markdown documentation files (repo-internal and standalone) as `document` objects.
- **1.1.3** Ingest git history: every commit becomes a first-class, searchable fact with author, date, message, and touched paths.

**Acceptance criteria:**
- Running `mkc ingest` against the `repos/` directory completes without error and indexes every text-readable file (skips binaries with a logged skip record).
- Each indexed file produces at least one knowledge object with `source_type = "git"` or `"markdown"` and `source_id = <repo-name>`.
- Re-running `mkc ingest` is idempotent: objects already present at the same `file_path` + `commit_hash` are not duplicated; changed files produce updated objects with new provenance.
- At least one sample commit is queryable via `mkc search "<commit-message-fragment>"` and returns the commit with full author/date metadata.

### 1.2 Provenance

- **1.2.1** Every knowledge object stores provenance: `source_type`, `source_id`, `file_path`, `commit_hash`, `author`, `date`.
- **1.2.2** Extraction records the method (`extraction_method`) and an `original_text` excerpt.

**Acceptance criteria:**
- A SQL check over the initial load shows zero `knowledge` rows with NULL `source_type` or NULL `source_id`.
- For any sampled object, following `file_path` + `commit_hash` back to the repo reproduces the cited `original_text` excerpt (verified manually for ≥10 samples).
- Provenance columns are not writable through the public API (PATCH cannot alter them).

### 1.3 Extraction

- **1.3.1** Extract structured entities from ingested content: **modules**, **engines**, **theories**, **metrics**.
- **1.3.2** Classify each extracted object with one of the 31 knowledge object types (see `KNOWLEDGE_MODEL.md`) and an initial lifecycle state (`idea`/`question`/`hypothesis` as appropriate — extraction never creates `validated` objects directly).

**Acceptance criteria:**
- `mkc status` reports counts by object type; at least `module`, `metric`, and `document` counts are non-zero after a full ingest.
- No extracted object has a lifecycle state beyond `hypothesis` unless backed by an ingested validation artifact (e.g., a test suite or benchmark file that itself claims it).
- Every extracted object links to at least one `document` object (its source).

### 1.4 Search

- **1.4.1** Full-text search over all indexed knowledge objects (title, body, `original_text`).
- **1.4.2** Exposed via CLI (`mkc search "query"`) and API (`GET /knowledge?...`).

**Acceptance criteria:**
- `mkc search "forecast engine"` returns relevant objects ranked by relevance, each with type, lifecycle state, and provenance in the output.
- Searches with no matches return an empty result set, not an error.
- Search works on content from at least 3 different repos simultaneously (cross-repo queries).
- NFR performance target: search < 200 ms p95 at 10K objects (see §NFR).

### 1.5 Research, Decisions, Experiments

- **1.5.1** Research items: create via `POST /research` and CLI; track open questions and research threads with lifecycle.
- **1.5.2** Decisions: create via `POST /decisions`; a decision stores rationale, options considered, and links to the evidence it rests on.
- **1.5.3** Experiments: create via `POST /experiments`; each experiment links to the hypothesis it tests.

**Acceptance criteria:**
- Creating each object type via API returns `201` with a populated provenance and lifecycle-state field.
- A decision can reference one or more knowledge objects as its evidence; the referenced objects are retrievable from the decision detail view.
- An experiment that references a hypothesis is visible from the hypothesis detail (bidirectional link).
- A decision can be superseded via `POST /decisions/{id}/supersede`, which links to the new decision and marks the old one `superseded` (never deletes it).

### 1.6 Contradiction Detection

- **1.6.1** Detect contradictory claim pairs during/after ingestion (e.g., two documents stating different values for the same metric or engine behavior).

**Acceptance criteria:**
- Seeding two conflicting statements about the same subject produces a recorded contradiction linking both objects, with a `severity` (initially `high`/`medium`/`low` per the detection method).
- The contradiction is visible via API/CLI and is never auto-resolved.

### 1.7 Insight Generation

- **1.7.1** Generate insights from the indexed corpus.

**Acceptance criteria:**
- After a full ingest, `insights` table is non-empty; each insight cites at least one supporting knowledge object.
- Insight types are one of: `pattern`, `trend`, `gap`, `contradiction`, `recommendation`.

### 1.8 Initial Reports

- **1.8.1** Generate the three inaugural reports:
  - `project-knowledge-YYYY-MM-DD.md` — what MKC currently knows: knowledge-object inventory, lifecycle distribution, top entities, provenance coverage.
  - `research-gaps-YYYY-MM-DD.md` — open questions, missing evidence, unvalidated hypotheses, undocumented areas.
  - `implementation-plan-YYYY-MM-DD.md` — prioritized next work derived from gaps, contradictions, and research state.
- **1.8.2** Reports are written to the MKC workspace and re-generable; regenerating never overwrites history (previous reports retained).

**Acceptance criteria:**
- `mkc reports` (or equivalent) produces all three files with the correct date suffix, each non-trivial (≥ 1 section of real content derived from live data, not template text).
- Every claim in the reports traces to at least one knowledge object id (spot-checked on ≥ 10 claims).

### 1.9 CLI

- **1.9.1** `mkc ingest` — run ingestion over configured sources.
- **1.9.2** `mkc search "query"` — full-text search with type/lifecycle filtering.
- **1.9.3** `mkc health` — connectivity and service health (API, DB).
- **1.9.4** `mkc status` — counts by object type and lifecycle state, last ingest time.

**Acceptance criteria:**
- All four commands work against a running stack and exit non-zero on failure with a human-readable error message.
- `mkc health` reports API up, DB up, and last successful ingest timestamp.
- Every command supports `--help` with accurate usage text.

### 1.10 API

- **1.10.1** Implement and expose: `POST /knowledge`, `GET /knowledge`, `GET /knowledge/{id}`, `POST /research`, `GET /research`, `POST /decisions`, `GET /decisions`, `POST /experiments`, `GET /experiments`, `GET /healthz`, `GET /metrics`, `GET /api/v1/status`.
- **1.10.2** All state-changing endpoints require a bearer token (`MKC_API_TOKEN`).

**Acceptance criteria:**
- `GET /healthz` returns 200 with `{"status":"ok",...}` and does not require auth.
- `GET /api/v1/status` returns object counts, last ingest time, and service versions without auth.
- `GET /metrics` exposes Prometheus-format metrics (see §NFR observability).
- Any state-changing request without a valid token returns 401; with a wrong token, 401 (not 403 or 500).
- `POST /knowledge` with an invalid `object_type` or `lifecycle_state` returns 422 with a descriptive error.
- Every 2xx knowledge response includes full provenance fields.

### 1.11 Documentation Foundation

- **1.11.1** Root `README.md` (overview, principles, quick start, what's next).
- **1.11.2** `docs/PRODUCT_BACKLOG.md` (this file), `docs/CHANGELOG.md`, `docs/KNOWLEDGE_MODEL.md` (types, lifecycle, provenance).
- **1.11.3** Skeletons with real section structure for `docs/ARCHITECTURE.md`, `docs/DEVELOPER_GUIDE.md`, `docs/API_REFERENCE.md`, `docs/OPS_RUNBOOK.md`, `docs/SECURITY_MODEL.md` — to be filled from working code in Waves 2/5/6.

**Acceptance criteria:**
- Quick start in `README.md` reproduces a working install → migrate → ingest → search flow on a clean environment.
- `KNOWLEDGE_MODEL.md` enum values match the backend models exactly (verified by diffing against `backend/` source).
- No "TODO"/"TBD" placeholders in the owned docs; skeletons contain real section structure and previews only.

### Milestone 1 Definition of Done

1. **Working ingestion** — repos + markdown + git history indexed (1.1).
2. **Working knowledge extraction** — modules/engines/theories/metrics extracted and classified (1.3).
3. **Working storage** — objects persist with complete provenance (1.2).
4. **Working search** — cross-repo full-text search, CLI + API (1.4).
5. **Working provenance** — every object traceable to source file + commit (1.2).
6. **Working research management** — research/decisions/experiments creatable and linked (1.5).
7. **Working contradiction detection** — conflict recorded, never auto-resolved (1.6).
8. **Working insight generation** — typed, cited insights (1.7).
9. **Working reports** — all three inaugural reports generated from live data (1.8).
10. **Working CLI** — `ingest`, `search`, `health`, `status` (1.9).
11. **Working API** — all listed endpoints, auth enforced (1.10).
12. **Working tests** — backend test suite passes (see §NFR quality).
13. **Working documentation** — this backlog, knowledge model, and skeletons in place (1.11).
14. **End-to-end demonstration** — the full pipeline (ingest → extract → search → context) demonstrated live, with evidence captured in `project-knowledge-YYYY-MM-DD.md`.

---

## Milestone 2: Intelligence

**Goal:** turn the corpus into a connected, queryable intelligence layer — graph links, semantic search, and analytic outputs (gaps, coverage scores).

### 2.1 Knowledge Graph

- **2.1.1** Populate `entity_relations` between knowledge objects using typed edges: `depends_on`, `uses`, `implements`, `tests`, `documents`, `related_to`.
- **2.1.2** Relations are created by the extraction/analysis pass; each relation records the method that created it.

**Acceptance criteria:**
- After a full analysis pass, `entity_relations` is non-trivial (≥ 1 relation per 10 knowledge objects).
- Each relation has: `source_id`, `target_id`, `relation_type` (one of the six above), `created_by` method, `confidence`.
- No relation is created between objects without provenance; invalid target ids are rejected with an error.
- A query path (e.g., module → depends_on → module → tests → experiment) returns the connected chain in ≤ 3 hops.

### 2.2 Semantic Search

- **2.2.1** Vector embeddings for knowledge objects using pgvector (if available in the environment; otherwise a documented fallback to ranked full-text with a capability flag in `GET /api/v1/status`).
- **2.2.2** Hybrid search: combine full-text and vector similarity, ranked result.

**Acceptance criteria:**
- `GET /knowledge?q=...&mode=hybrid` (or equivalent parameter) returns semantically related objects that keyword search alone would miss (verified on a scripted test set of ≥ 10 queries).
- `GET /api/v1/status` reports `semantic_search: enabled|fallback` so callers know which mode is active.
- Embedding generation failures degrade to full-text search with a logged warning — never a 500.

### 2.3 Contradiction Detection (Enhanced)

- **2.3.1** Systematic claim-vs-claim comparison (`claim_a` vs `claim_b`) with `severity` ∈ {`high`, `medium`, `low`}.
- **2.3.2** Severity assignment rules documented in `KNOWLEDGE_MODEL.md`.

**Acceptance criteria:**
- Severity `high` is reserved for contradictions that would change implementation behavior if wrongly resolved; each high-severity contradiction is surfaced in the `research-gaps` report.
- Contradictions are paginable and filterable by severity via API.
- Re-running detection does not duplicate existing contradiction records (deduped on the pair + claim scope).

### 2.4 Insight Generation (Enhanced)

- **2.4.1** Insight types: `pattern`, `trend`, `gap`, `contradiction`, `recommendation`.
- **2.4.2** Every insight cites its supporting objects and the analysis run that produced it.

**Acceptance criteria:**
- Each of the five insight types is either produced or explicitly reported as "not observed in current corpus" (never silently absent).
- Insights are append-only: a new analysis run adds insights; it never mutates or deletes earlier ones (superseding is done by link, with the old one marked `superseded`).

### 2.5 Research Gap Analysis

- **2.5.1** Compute research gaps: open questions with no linked experiment, unvalidated hypotheses past a threshold age, domains with zero coverage, documented components with no tests.

**Acceptance criteria:**
- `research-gaps-YYYY-MM-DD.md` lists every gap with: the gap, the affected objects (with ids), and a suggested next investigation.
- Gaps are deterministic: running the analysis twice on the same data produces the same gap set.

### 2.6 Documentation Coverage Scoring

- **2.6.1** Score each module/subsystem for documentation coverage: files present, README presence, doc-vs-code ratio, provenance completeness.
- **2.6.2** Coverage scores are knowledge objects (`metric` type) so they themselves are searchable and versioned.

**Acceptance criteria:**
- Every repo under `repos/` has a coverage score in 0–100 with a breakdown (what it is and isn't measuring).
- Scores are stored as `metric` objects with provenance pointing at the analysis run.
- The lowest-scoring repos appear in the `implementation-plan` report with remediation tasks.

### Milestone 2 Definition of Done

1. `entity_relations` populated with all six typed edge kinds, queryable, and cited.
2. Semantic (or documented fallback) search working; hybrid mode returns better results than keyword-only on the test set.
3. Contradiction detection with severity, deduped, and surfaced in reports.
4. All five insight types producible; insight history append-only.
5. Research gap analysis deterministic and reported.
6. Documentation coverage scoring live and fed into the implementation-plan report.
7. Full regression: Milestone 1 acceptance criteria still pass unchanged.

---

## Milestone 3: Automation + Dashboard

**Goal:** a human-facing web UI over the API, so engineers can browse, search, and audit knowledge without a terminal.

### 3.1 Web Dashboard (React + TypeScript, under `web/`)

Nine modules, each backed by the existing API:

- **3.1.1 Overview** — knowledge health scores (provenance completeness, contradiction count, lifecycle distribution chart), headline numbers (objects, repos indexed, last ingest).
- **3.1.2 Knowledge** — browse/search knowledge objects; detail view shows full provenance, original_text excerpt, links, and lifecycle history.
- **3.1.3 Research** — research items with lifecycle state, open/closed filtering, linked evidence.
- **3.1.4 Experiments** — experiment tracking: hypothesis link, status, results, verdict; failed experiments displayed prominently (never hidden).
- **3.1.5 Decisions** — decision registry with rationale chains: decision → reason → evidence → experiment → implementation → commit; superseded decisions shown with their successors.
- **3.1.6 Insights** — insight feed grouped by type, each with supporting citations.
- **3.1.7 Planning** — implementation plan view: prioritized tasks derived from gaps, with owner/status where known.
- **3.1.8 Search** — faceted search UI (object type, lifecycle state, repo, source type, date range).
- **3.1.9 System Health** — API health, DB status, last ingest, metric snapshots.

**Acceptance criteria:**
- The app builds (`tsc` + production build) with no type errors and runs against the live API with bearer-token auth configured at the client.
- Every module renders real data (no mock data in production mode); empty states are explicit ("no objects of this type yet"), not blank screens.
- The Knowledge detail view shows provenance that, when followed by hand, reproduces the cited text in the source repo (spot-check ≥ 5 objects).
- Decision registry renders the full rationale chain for the seeded demo decision, including the supersede link.
- No console errors on first load of each of the nine views.
- Dashboard deployment target: static build served on the same host, behind the same bearer-token flow as the API (see `SECURITY_MODEL.md` when filled in Wave 5).

### 3.2 Automation

- **3.2.1** Scheduled re-ingest (cron/systemd timer) of `repos/` with a `mkc status` report after each run.
- **3.2.2** Weekly regeneration of the three reports (project-knowledge, research-gaps, implementation-plan) with a note when content is unchanged from the previous run.

**Acceptance criteria:**
- The timer runs unattended for ≥ 7 days without manual intervention; failures are logged and visible via `GET /metrics` (failed-run counter).
- Re-ingest is idempotent (re-verified: no duplicate objects after N scheduled runs).

### Milestone 3 Definition of Done

1. All nine dashboard views functional against the live API with real data.
2. No mock data in production; empty states explicit.
3. Provenance verifiable from the UI (detail view → source repo).
4. Scheduled re-ingest and weekly report generation running unattended.
5. Full regression: Milestones 1–2 acceptance criteria still pass.

---

## Non-Functional Requirements

### Performance

| Target | Value | Measured at |
|--------|-------|-------------|
| Full-text search | < 200 ms p95 | 10K knowledge objects |
| API request (any `GET /knowledge*`) | < 1 s p95 | 10K objects, local network |
| Ingest (full re-scan of 11 repos) | < 30 min | full corpus |
| Report generation (all three) | < 5 min | full corpus |

- Load targets validated in Wave 4 (QA) with a scripted load test; results recorded in the QA report.

### Security

- **Auth:** bearer token (`MKC_API_TOKEN`) required on all state-changing endpoints and (by default) on all data endpoints; only `/healthz`, `/metrics`, `/api/v1/status` are unauthenticated by default.
- **No secrets in code:** tokens, DB passwords, and API keys come from environment variables or a secret store — never committed, never in docs examples as real values.
- **Input validation:** all request bodies validated against Pydantic schemas; invalid enum values rejected with 422; path parameters validated before DB access.
- **Rate limiting:** minimum 60 requests/minute per client on authenticated endpoints (tunable via env); excess returns 429 with `Retry-After`.
- Full model in `SECURITY_MODEL.md` (filled in Wave 5).

### Observability

- **Structured logging:** JSON log lines (level, timestamp, event, duration_ms, object counts where relevant) from both API and CLI.
- **Metrics:** Prometheus format at `GET /metrics` — at minimum: request count/duration by route, ingest runs (total, failures, duration), object counts by type and lifecycle state, last-ingest timestamp.
- **Health:** `/healthz` (liveness, no auth) and `GET /api/v1/status` (readiness + counts + capability flags, no auth).

### Scalability

- 100K knowledge objects on a single server without architectural change: indexed search (GIN/tsvector + pgvector where enabled), no N+1 query patterns in hot paths, pagination (cursor or offset+limit) on all list endpoints, default page size ≤ 100.

### Quality

- Backend test suite passing with coverage ≥ 70% on the app package (target ≥ 85% in Wave 4).
- No test skipped without a recorded reason in the test file.

---

## Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Extraction produces low-quality or hallucinated "knowledge" from code/comments | High | High | Extraction is rule-based + LLM-assisted with mandatory `original_text` citation; no object may lack provenance; manual spot-check sampling in QA (Wave 4); lifecycle caps extracted objects at `hypothesis` |
| R2 | Contradiction detection creates noise (false positives erode trust) | High | Medium | Severity tiers; high-severity only in reports; human review pass before any contradiction influences a recommendation; false positives are recorded as `rejected` insights, not deleted |
| R3 | Provenance drift: repos re-cloned or history rewritten, breaking commit-hash links | Medium | Medium | `file-master-index.json` pins the indexed state; ingest records the exact commit hash per file; broken links are surfaced as a health warning, not silently dropped |
| R4 | Corpus growth outpaces single-server capacity (100K+ objects, embeddings) | Medium | Medium | NFR sets the 100K bound; pgvector on PostgreSQL keeps search in-DB; Wave 6 adds monitoring with capacity thresholds; document the scaling path (partitioning/second node) in ARCHITECTURE |
| R5 | AI-generated reports/insights drift from actual codebase | Medium | High | Every report claim must cite a knowledge object id; `project-knowledge` report includes a provenance-coverage section; contradiction between report and source is a defect, tracked in the risk register's review |
| R6 | Secret leakage (tokens/DB creds) into repos, logs, or docs | Medium | High | Env-only secrets policy; log redaction of token fields; secret scan in CI (Wave 4/5); docs use `change-me` placeholders only |
| R7 | Ingest of the 11 repos is expensive enough to block interactive use | Medium | Low | Incremental ingest keyed on commit hash; scheduled full re-scan off-peak (Milestone 3 automation); ingest runs report progress and are cancellable |
| R8 | Scope creep: "knowledge core" becomes a general-purpose wiki | Medium | Medium | Milestone boundaries + Definition of Done; backlog items without provenance value are deferred; product principles in README are the acceptance filter |
| R9 | pgvector unavailable in the environment | Low | Low | Documented fallback to ranked full-text search with a capability flag in `/api/v1/status` (Milestone 2.2); feature is optional, not blocking |
| R10 | Single-maintainer bus factor on the Momento stack MKC describes | Medium | Medium | The documentation and knowledge model are designed for a competent newcomer (day-2 audience); `DEVELOPER_GUIDE.md` and `OPS_RUNBOOK.md` are DoD items, not nice-to-haves |

---

## Backlog Hygiene

- This file is updated when a milestone completes (move completed items into the changelog with their evidence) and when scope changes are agreed.
- An item is "done" only when every acceptance criterion has passing evidence (test output, command output, or a captured demonstration) — "code compiles" is not done.
