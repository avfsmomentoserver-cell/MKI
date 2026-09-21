# MKC API Reference

> **Status: skeleton with the real endpoint inventory (documentation foundation wave).** The endpoint list, auth model, and shared shapes below are the Milestone 1 contract. Wave 2 adds full request/response schemas, error envelopes, and examples captured from the working code.

## 1. Overview

- **Base URL:** `http://127.0.0.1:8000` (local bind; firewall policy governs remote access in production)
- **Transport:** HTTP/1.1 (Milestone 1); all bodies are JSON
- **Content type:** `application/json` for all request/response bodies
- **API prefix:** object endpoints are served at the root path (`/knowledge`, `/research`, …) with `/api/v1/status` as the versioned status surface

### Authentication

- **Scheme:** bearer token. Send `Authorization: Bearer <token>`; the token is the value of `MKC_API_TOKEN` from `.env` (see `ops/ENVIRONMENT.md` §3).
- **Required on:** every state-changing endpoint (`POST`, `PATCH`) and every data endpoint (`GET /knowledge*`, `GET /research*`, `GET /decisions*`, `GET /experiments*`).
- **Not required on:** `/healthz`, `/metrics`, `/api/v1/status` (ops surface).
- **Failure:** a missing or invalid token yields `401 Unauthorized` with a JSON error body — never `403` and never `500`.
- **Token handling:** the token comes from the environment (`.env`); it is never logged, never returned by any endpoint, and never stored in knowledge objects.

### Errors and Validation

- All request bodies are validated against typed Pydantic schemas; invalid enum values (`object_type`, `lifecycle_state`, …) yield `422` with a field-level error message.
- Unknown object ids yield `404` with a JSON error body.
- Rejected lifecycle transitions yield `409` with the allowed transitions in the detail.
- Every error response has the shape `{"error": "<code>", "detail": "<human-readable message>"}` (Wave 2 confirms the exact envelope from the code).

### Pagination

List endpoints accept `limit` (default and maximum ≤ 100 per the NFR) and an offset/cursor parameter. Wave 2 documents the exact parameter names and the response meta convention.

## 2. Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/knowledge` | yes | Create a knowledge object (any of the 31 object types). Requires a valid `object_type`, initial `lifecycle_state`, and at least `source_type` + `source_id` provenance; the server records `extraction_method` and `original_text` when supplied. |
| `GET` | `/knowledge` | yes | List/search knowledge objects. Query filters: full-text `q`, `object_type`, `lifecycle_state`, `source_id` (repo), `source_type`, `limit`, offset. Returns ranked, paginated results with full provenance. |
| `GET` | `/knowledge/{id}` | yes | Retrieve one knowledge object with full provenance, `original_text` excerpt, relations, and lifecycle history. |
| `PATCH` | `/knowledge/{id}` | yes | Update mutable fields (e.g., promote along an allowed lifecycle transition, edit derived fields). Provenance fields are immutable — attempts to change them are rejected (`422`); rejected lifecycle transitions return `409`. |
| `POST` | `/research` | yes | Create a research item (open question / research thread) with lifecycle state and optional links to supporting knowledge objects. |
| `GET` | `/research` | yes | List research items with lifecycle filter and pagination. |
| `GET` | `/research/{id}` | yes | Retrieve one research item including its linked evidence and status. |
| `POST` | `/decisions` | yes | Create a decision with rationale, options considered, and links to the evidence knowledge objects it rests on. |
| `GET` | `/decisions` | yes | List decisions (including superseded ones — history is never hidden) with filter by status. |
| `GET` | `/decisions/{id}` | yes | Retrieve one decision with its full rationale chain: reason → evidence → experiment → implementation links, and a `superseded_by` pointer when set. |
| `POST` | `/decisions/{id}/supersede` | yes | Record that decision `{id}` is superseded by the decision named in the body. Marks the old decision `superseded` and links it to the new one; the original record is preserved permanently. |
| `POST` | `/experiments` | yes | Create an experiment tracking record linked to the hypothesis (knowledge object) it tests, with method and expected outcome. |
| `GET` | `/experiments` | yes | List experiments with status filter (running, passed, failed, rejected); failed experiments are always returned — they are evidence. |
| `GET` | `/experiments/{id}` | yes | Retrieve one experiment with hypothesis link, results, and verdict. |
| `POST` | `/experiments/{id}/validate` | yes | Record the outcome of experiment `{id}` (pass/fail with results). A pass may advance the linked hypothesis along the lifecycle if the transition rules allow; a fail records the failure without deleting anything. |
| `GET` | `/healthz` | no | Liveness probe. Returns `200` with `{"status": "ok", ...}`. No auth, no full DB dependency beyond a connectivity check. |
| `GET` | `/metrics` | no | Prometheus-format metrics: request counts/durations by route, ingest run counters (total, failures, duration), object counts by type and lifecycle state, last-ingest timestamp. |
| `GET` | `/api/v1/status` | no | Readiness + corpus status: object counts, last ingest time, service versions, and capability flags (e.g., `semantic_search: enabled|fallback`). |

## 3. Shared Shapes

### Knowledge object (response, all object endpoints)

```json
{
  "id": "<uuid>",
  "object_type": "module",
  "lifecycle_state": "hypothesis",
  "title": "...",
  "content": "...",
  "provenance": {
    "source_type": "git",
    "source_id": "momento-core",
    "file_path": "backend/momento/forecasting/engine.py",
    "commit_hash": "<40-hex>",
    "author": "...",
    "date": "2026-09-18T12:00:00Z",
    "extraction_method": "rule:module-header",
    "original_text": "..."
  },
  "relations": [ { "type": "depends_on", "target_id": "<uuid>" } ],
  "created_at": "...",
  "updated_at": "..."
}
```

### Error body

```json
{ "error": "invalid_lifecycle_transition", "detail": "hypothesis cannot transition directly to validated" }
```

Wave 2 replaces these sketches with the exact schemas (field-by-field, with every enum value) and one real request/response example per endpoint, captured from the running API.

## 4. AI Context API

Milestone 1 ships the context assembly as part of the intelligence layer: given a query, it returns the ranked knowledge objects plus their citations, in a shape designed to be pasted into an LLM prompt (VS Code agents, Devin, or a future agent endpoint). Wave 2 documents the exact response shape and the token-budget parameter; the product goal is the "ask MKC" workflow in the root `README.md`.
