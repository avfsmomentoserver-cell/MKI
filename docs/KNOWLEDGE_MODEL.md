# MKC Knowledge Model

> **Status: canonical reference (documentation foundation wave).** The enum values below are the contract for the Wave 1b models; the Architect wave (Wave 2) cross-checks them against `backend/` source and keeps this file as the single source of truth for *semantics*.

The MKC knowledge model has three parts:

1. **Object types** — what a knowledge object *is* (31 types).
2. **Lifecycle states** — where a knowledge object *stands* in the evidence lifecycle (10 active states + 4 terminal states + 1 catch-all).
3. **Provenance** — where a knowledge object *came from* and how it was extracted (immutable).

A knowledge object is never just text: it is (type, state, content, provenance, relations).

---

## 1. Object Types

The 31 object types, grouped by purpose. An object's `object_type` is fixed at creation; changing type is a new object (supersession), not an edit.

### Ingested content

| Type | Meaning |
|------|---------|
| `document` | A unit of ingested content: a markdown file, a source file, a chatgpt conversation export, a paper. The base type — most other objects cite a `document`. |
| `source` | An external citation target (paper, article, dataset publication) that knowledge claims reference. |
| `dataset` | A data collection (recordings, CSV exports, benchmark inputs) that experiments or metrics draw on. |
| `glossary_term` | A defined term used across the corpus, with its canonical definition and where it appears. |

### Claims about the world (the evidence lifecycle lives here)

| Type | Meaning |
|------|---------|
| `fact` | A statement asserted as true by its source, with provenance to the source. Facts are *as-reported*, not independently verified. |
| `claim` | A debatable assertion — a statement that may be true or false, and that contradiction detection operates on. |
| `hypothesis` | A proposed explanation or prediction that has not yet been tested. The entry point to the experimental lifecycle. |
| `question` | An open research question. The trigger for a research item. |
| `theory` | A body of related hypotheses/facts forming an explanatory model (e.g., a compression-based forecasting model). |
| `observation` | A recorded empirical observation from running something (not yet the controlled result of an `experiment`). |
| `insight` | A derived finding — a `pattern`, `trend`, `gap`, `contradiction`, or `recommendation` — produced by analysis, always citing its supporting objects. |
| `research` | A research thread: a question plus the evidence gathered so far, with its own lifecycle. |
| `paper` | A specific ingested research paper (distinct from `source`, which is a generic citation target). |
| `experiment` | A controlled test of a hypothesis: method, conditions, results, verdict. Failed experiments are preserved, never deleted. |

### Engineering knowledge

| Type | Meaning |
|------|---------|
| `decision` | A recorded decision with rationale, options considered, and evidence links. Superseded, never overwritten. |
| `requirement` | A stated requirement (functional or non-functional) with its origin. |
| `module` | A code module/subsystem identified by extraction (e.g., the Forecast Engine). |
| `dependency` | A stated dependency between components (library, service, or data dependency). |
| `implementation` | A concrete implementation of a decision, requirement, or theory, linked to the code (file path + commit hash). |
| `benchmark` | A measured performance/quality result for a module or approach, with inputs and conditions. |
| `bug` | A recorded defect with its symptom, diagnosis, and fix (or open state). |
| `risk` | A known risk to the project, with likelihood/impact and mitigation. |
| `tech_debt` | A known deviation from the intended design, with its cost and planned resolution. |
| `plan` | A plan for future work, derived from insights and gaps. |
| `task` | A unit of work inside a plan. |
| `roadmap_item` | A milestone-level item in the project roadmap. |

### Measurement

| Type | Meaning |
|------|---------|
| `metric` | A measured quantity (e.g., search latency, documentation coverage score) with its unit, measurement method, and value. Coverage scores from analysis are stored as `metric` objects so they themselves are searchable. |

### People and projects

| Type | Meaning |
|------|---------|
| `person` | A contributor/author/decision-maker referenced across objects (linked from provenance `author` and from decisions). |
| `project` | A project boundary (e.g., `momento-core`, `MomentoFX`) — the top-level grouping for repos and their knowledge. |
| `subsystem` | A named subsystem within a project, finer-grained than `module` (e.g., "commercial API" within MomentoFX). |

---

## 2. Lifecycle States

The lifecycle separates *hypothesis* from *validated knowledge*. The active path is a forward-moving chain; terminal states are absorbing (an object in a terminal state is never edited — corrections are new objects that supersede it).

### Active chain (10 states)

```
idea -> question -> hypothesis -> researching -> experiment
  -> observed -> validating -> validated -> implemented -> production
```

| State | Meaning |
|-------|---------|
| `idea` | A raw notion, not yet articulated as a testable question. |
| `question` | An articulated open question, eligible for a research thread. |
| `hypothesis` | A falsifiable proposed answer/explanation. **Extraction never creates objects past this state** unless backed by an ingested validation artifact. |
| `researching` | Active investigation in progress; evidence is accumulating. |
| `experiment` | A controlled test is defined or running against this hypothesis. |
| `observed` | Empirical observations have been recorded, not yet confirmed under controlled conditions. |
| `validating` | The observations are being checked (reproduction, independent validation, review). |
| `validated` | Evidence supports the claim under stated conditions. *Validated is not "true" — it means "evidence-backed within scope."* |
| `implemented` | The validated knowledge is realized in code (linked to an `implementation` object + commit). |
| `production` | In production use; the end of the active chain. Production objects may still accumulate new observations. |

### Terminal states (4) + catch-all

| State | Meaning |
|-------|---------|
| `contradicted` | Confirmed contradiction with stronger or newer evidence; the contradicting object(s) are linked. The object is preserved for the record. |
| `rejected` | Investigated and rejected (e.g., a failed experiment whose hypothesis is abandoned). Preserved — a negative result is evidence. |
| `deprecated` | Was valid, no longer in use or relevant (e.g., a replaced approach). |
| `superseded` | Replaced by a newer object; the superseding object is linked (`superseded_by`). Original content is preserved permanently. |
| `unknown` | Lifecycle could not be determined at extraction time. **Catch-all, not a destination** — it must be resolved to an active or terminal state during review; it is not a lifecycle end state. |

### Transition rules (enforced by the backend state machine)

- Forward movement along the active chain requires the evidence for the next stage to exist (e.g., `hypothesis -> experiment` requires a linked `experiment`; `observed -> validating` requires linked `observation` objects).
- **No skipping**: there is no `hypothesis -> validated` jump.
- Any active state may enter a terminal state with a linking record explaining why.
- Terminal states are absorbing: no transitions out, except a manual review action that creates a *new* object (supersession) — the terminal object itself is never mutated.
- Every transition is audit-logged: who/what (user, analysis run, API caller), when, and the evidence that justified it.
- `PATCH /knowledge/{id}` is the only public mutation path for lifecycle; rejected transitions return `409`.

---

## 3. Provenance

Every knowledge object carries an immutable provenance record. Provenance answers: *where did this come from, and how do I check it?*

| Field | Type | Meaning |
|-------|------|---------|
| `source_type` | enum | The kind of source: `git` (a file in a repo), `git_commit` (a commit itself), `markdown` (standalone doc), `chatgpt` (a conversation export), `paper`, `api` (created via the API by a user/agent), `analysis` (produced by an MKC analysis run — insights, coverage scores). |
| `source_id` | string | The source identifier: repo name (e.g., `momento-core`) for `git`, the commit SHA for `git_commit`, the file path for `markdown`/`chatgpt`, the paper id for `paper`, the API caller id for `api`, the analysis-run id for `analysis`. |
| `file_path` | string | Path of the cited file within the source (repo-relative). |
| `commit_hash` | string (40-hex) | The exact commit the file content was read from. This is what makes re-ingestion idempotent and provenance verifiable after history changes. |
| `author` | string | Author of the cited content (git author name/email, conversation author, or analysis run). |
| `date` | timestamp | Date of the cited content (commit date, file date, or analysis run date). |
| `extraction_method` | string | How the object was produced: `ingest` (direct file→document), `rule:<name>` (a named extraction rule, e.g., `rule:module-header`), `llm:<model>` (LLM-assisted, model identified), or `manual` (created by a human via API/CLI). LLM-assisted extraction is always flagged so downstream consumers know the confidence class. |
| `original_text` | text (excerpt) | The verbatim excerpt from the source the object was derived from. This is the audit anchor: a reader can find this text in the cited file at the cited commit. |

### Provenance rules

- **Immutable.** Provenance fields cannot be changed through the API (`PATCH` rejects them with `422`). Correction means a new object.
- **Mandatory.** `source_type` and `source_id` are required on every object; no object exists without provenance.
- **Verifiable.** `file_path` + `commit_hash` must resolve to a file whose content contains `original_text`. Broken links (repo re-cloned, history rewritten) are surfaced as health warnings, never silently dropped.
- **Extraction cap.** An object created by extraction (any `extraction_method` other than `manual`) starts at or below `hypothesis` in the lifecycle, unless it cites a `document` that is itself a validation artifact (test suite, benchmark, signed-off report).

### Confidence (orthogonal to lifecycle)

Every object also carries a confidence score 0–100 with a band label: `unknown`, `low`, `medium`, `high`, `validated`, `verified`, `production_proven`. Confidence reflects the *strength of evidence* (number of independent sources, experiment results, production time, consistency) and moves independently of lifecycle state — an object can be `validated` with `medium` confidence, or `observed` with `high` confidence.

---

## 4. Relations

Objects connect through typed edges in `entity_relations` (populated in Milestone 2). The six relation types: `depends_on`, `uses`, `implements`, `tests`, `documents`, `related_to`. Each relation records its creator (extraction rule or analysis run) and a confidence value. The full cardinality and index design is in `ARCHITECTURE.md` §6 (Wave 2).

## 5. Contradictions

A contradiction is a first-class record: `claim_a` (object id), `claim_b` (object id), `severity` ∈ {`high`, `medium`, `low`}, the detection method, and the date. Severity `high` is reserved for contradictions that would change implementation behavior if wrongly resolved; high-severity contradictions always appear in the `research-gaps` report. Contradictions are never auto-resolved — resolution is a human decision, recorded as a new `decision` object that links both sides.

## 6. Insights

An insight is a knowledge object of type `insight` with a subtype: `pattern`, `trend`, `gap`, `contradiction`, `recommendation`. Every insight cites at least one supporting knowledge object and the analysis run that produced it. Insights are append-only: a new analysis run adds insights; it never mutates or deletes earlier ones (superseding is done by link, marking the old insight `superseded`).
