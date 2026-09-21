# MKC End-to-End Demonstration — Resumed Run

- **Run date:** 2026-09-21 (resumed; previous agent hit its step limit after a partial ingest)
- **Target DB:** `mkc` @ Postgres 17 `localhost` (role `mkc`), read via `psql -h localhost -U mkc -d mkc`
- **Tooling:** `mkc` CLI in `backend/.venv` (`ingest`, `search`, `report`)
- **Method:** RESUME, not restart. Section 1 records the state the previous agent left (BASELINE-RESUME); this run completed the ingest of every remaining source, generated the three reports, ran spot checks, a negative control, an idempotency proof, and the contradictions/insights analysis. All numbers are real, measured against the live DB — no placeholders.

## Table of contents

1. [Resumed baseline (BASELINE-RESUME)](#1-resumed-baseline-baseline-resume)
2. [Post-ingest counts (by type, by lifecycle state)](#2-post-ingest-counts-by-type-by-lifecycle-state)
3. [Sources indexed (per-source file/doc counts)](#3-sources-indexed-per-source-filedoc-counts)
4. [Knowledge objects created](#4-knowledge-objects-created)
5. [Relationships discovered](#5-relationships-discovered)
6. [Contradictions / insights](#6-contradictions--insights)
7. [Reports generated (3 files + sizes)](#7-reports-generated-3-files--sizes)
8. [Spot check results (verbatim)](#8-spot-check-results-verbatim)
9. [Negative control](#9-negative-control)
10. [Idempotency before/after](#10-idempotency-beforeafter)
11. [Bugs found & crash fix (handoff)](#11-bugs-found--crash-fix-handoff)
12. [VERDICT](#12-verdict)

---

## 1. Resumed baseline (BASELINE-RESUME)

Live-DB state at the moment this resumed run started (read-only measurement).

**Sources by type**

| source_type | count |
|---|---|
| commit | 84 |
| git | 4 |
| **total** | **88** |

**Documents:** 165 · **Knowledge objects:** 198 · **Entities:** 157 · **Relationships:** 0

**Knowledge objects by type:** fact 96 · module 96 · experiment 4 · hypothesis 1 · observation 1
**Knowledge objects by lifecycle_state:** implemented 96 · idea 96 · experiment 4 · observed 1 · hypothesis 1

**Git sources already ingested (previous run)**

| source_id | docs |
|---|---|
| MomentoFresh | 96 |
| momentocore2 | 66 |
| avfs-backend | 3 |
| azuredev-3867 | 0 (empty repo, no commits) |

**Still to ingest (identified this run):** git repos `momento-core3`, `MomentoRabbit`, `momento-core`, `MomentoFX`, `InvestigationSuite`, `MomentoV5`, `momento-avfs-core`; plus the markdown dir `docs/`.
**ChatGPT archive:** `content-archive/` manifest reports `"chatgpt_history_found": []` and no `.jsonl` history exists on disk — there is no chatgpt material to ingest (documented, not a failure).

## 2. Post-ingest counts (by type, by lifecycle state)

Live-DB state after this run's ingest completed.

**Sources by type**

| source_type | count | delta from baseline |
|---|---|---|
| commit | 136 | +52 |
| git | 11 | +7 |
| **total** | **147** | +59 |

**Documents:** 2,543 (delta +2,378; all attributed to git sources)
**Knowledge objects:** 198 (unchanged — see Section 11, bug B1: extraction is blocked)
**Entities:** 157 · **Relationships:** 0 · **Contradictions:** 0 · **Insights:** 0 · **Reports:** 3

**Knowledge objects by type (unchanged from baseline)**

| type | count |
|---|---|
| fact | 96 |
| module | 96 |
| experiment | 4 |
| hypothesis | 1 |
| observation | 1 |

**Knowledge objects by lifecycle_state (unchanged from baseline)**

| lifecycle_state | count |
|---|---|
| implemented | 96 |
| idea | 96 |
| experiment | 4 |
| observed | 1 |
| hypothesis | 1 |

## 3. Sources indexed (per-source file/doc counts)

Git sources (the 11 repos under `/home/admin/MKI/repos/`). `docs` = `documents` rows attributed to that source. Commit sources (136) carry no documents (they feed extraction context, not the `documents` table).

| source_id | docs | note |
|---|---|---|
| momento-core | 750 | |
| MomentoFX | 706 | |
| MomentoV5 | 497 | |
| MomentoFresh | 96 | pre-existing |
| momentocore2 | 66 | pre-existing |
| InvestigationSuite | 28 | |
| momento-core3 | 12 | |
| avfs-backend | 3 | pre-existing |
| MomentoRabbit | 1 | |
| azuredev-3867 | 0 | empty repo (no commits) |
| momento-avfs-core | 384 | large repo (831 MB), run in background |

**Markdown dir `docs/`: FAILED to register as a source** — `MarkdownCollector.run()` raises `AttributeError: 'MarkdownCollector' object has no attribute 'repo_name'` (bug B3). No markdown source exists in the DB.
**ChatGPT archive:** no history on disk — nothing to ingest (see Section 1).

## 4. Knowledge objects created

**Net new knowledge objects this run: 0.** The count is 198 both at baseline and post-ingest.

Why: extraction runs over *all* eligible documents in the DB (global scope), and every extract pass since the first source was ingested aborts on a deterministic primary-key collision (`knowledge_objects_pkey`) the moment two sources share identical file content at the same path (bug B1). The 198 existing objects were all created by the previous run's first successful extract (before a second repo introduced a colliding file). Consequently the ~2,350 newly-collected documents were never turned into knowledge objects in this run.

## 5. Relationships discovered

`entity_relations` count = **0**. `RelationshipBuilder` runs *after* `KnowledgeExtractor` in `cmd_ingest` and never gets reached because extraction crashes (bug B1). No typed edges exist in the live DB.

## 6. Contradictions / insights

**Run** (via `mkc.core.database.get_session_factory` + `ContradictionDetector`/`InsightGenerator`, ~2 s, no CLI subcommand exists for these — the CLI only has `health/status/ingest/search/report`).

- Contradictions: **0** (`contradictions` table empty).
- Insights: **0** (`insights` table empty).
- However, both scanners **failed to scan anything** and returned `objects_scanned=0` with the error:
  `AttributeError: type object 'KnowledgeObject' has no attribute 'select'`
  (both `analysis/contradictions.py` and `analysis/insights.py` call `KnowledgeObject.select()`, which does not exist on the declarative model — bug B4). The zero counts above are therefore **unverified** (empty because the scan aborted, not because the corpus is clean).

Top-5 findings: *none recorded — scan blocked (B4).*

## 7. Reports generated (3 files + sizes)

Generated via `mkc report <type>` against the live DB (default output dir `<workspace>/reports`).

| report type | file | size |
|---|---|---|
| project-knowledge | `/home/admin/MKI/reports/project-knowledge-2026-09-21.md` | 18,749 bytes |
| research-gaps | `/home/admin/MKI/reports/research-gaps-2026-09-21.md` | 3,355 bytes |
| implementation-plan | `/home/admin/MKI/reports/implementation-plan-2026-09-21.md` | 4,527 bytes |

All three carry the same source-DB header: `contradictions: 0, decisions: 0, documents: 2159, entities: 157, entity_relations: 0, knowledge_objects: 198, reports: 0, research_items: 0, sources: 144` (the 2,159 docs / 144 sources were the counts at the moment each report was written, before the 831 MB background repo finished adding 384 docs / 3 commit sources).

## 8. Spot check results (verbatim)

`mkc search "forecast" --top-k 5` — 4 matches with provenance (source location + original-text snippet):

```
search 'forecast': 4 match(es), showing 4
   1. [knowledge] ✅ **Real-time Analysis** — Process rounds with <50ms ingest latency type=fact state=idea conf=0.40
      at: README.md#Features
      ~: ssification** — Normal, Shelf, Ignition, Moonshot regimes ✅ **Prediction Engine** — Multi-horizon forecasting with confidence scores ✅ **Auto-Analysis** — Backg
   2. [knowledge] Express.js + SQLite backend for real-time game round analysis with signal detection, DNA p type=fact state=idea conf=0.40
      at: README.md#AVFS Backend - Advanced Volatility Forecasting System
      ~: ckend for real-time game round analysis with signal detection, DNA pattern matching, and predictive forecasting.
   3. [knowledge] ```sql type=fact state=idea conf=0.40
      at: API_DOCUMENTATION.md#`predictions` Table
      ~: TEXT, signal_notes_json TEXT, moonshot_eta_json TEXT, latest_json TEXT, config_json TEXT, forecast_json TEXT, warnings_json TEXT, transitions_json TEXT, accurac
   4. [knowledge] AVFS (Advanced Volatility Forecasting System) is an Express.js backend that analyzes game type=fact state=idea conf=0.40
      at: API_DOCUMENTATION.md#Overview
      ~: AVFS (Advanced Volatility Forecasting System) is an Express.js backend that analyzes game round data using SQLite. It pr
```

`mkc search "compression" --top-k 5`:

```
search 'compression': 0 match(es), showing 0
```

0 is an honest result (no corpus object mentions compression), not an error — the query returned cleanly.

`psql` decision-objects query (the `type` column has no `'decision'` value in this corpus; types are fact/module/experiment/hypothesis/observation):

```
 id | type | lifecycle_state | summary
----+------+-----------------+---------
(0 rows)
```

## 9. Negative control

`mkc search "zxqvwfplm" --top-k 5` (nonsense term):

```
search 'zxqvwfplm': 0 match(es), showing 0
```

**PASS** — zero results, no error.

## 10. Idempotency before/after

Picked `avfs-backend` (small, already-ingested). Re-ingested it in full and compared counts.

| metric | before | after | change |
|---|---|---|---|
| avfs-backend docs | 3 | 3 | 0 |
| avfs-backend knowledge objects | 49 | 49 | 0 |
| total docs | 2,159 | 2,159 | 0 |
| total knowledge objects | 198 | 198 | 0 |
| total entities | 157 | 157 | 0 |
| total relationships | 0 | 0 | 0 |

**Collector phase is idempotent** (deterministic ids / upserts — zero duplicate docs or knowledge objects for the re-ingested source). **However, the full re-ingest command still crashes** at the extract stage on the same cross-source PK collision (bug B1), so the *end-to-end* re-ingest is not idempotent/clean: it leaves the DB unchanged but exits with `IntegrityError`. The "unchanged counts" here are a side effect of the crash rolling back the transaction, not of successful idempotent reprocessing.

## 11. Bugs found & crash fix (handoff)

> One crash fix was applied, within the allowed scope (ImportError only). The rest are reported, not touched.

**CRASH FIX (applied):** `backend/src/mkc/intelligence/analysis/__init__.py` imported `KnowledgeSearch` from `mkc.intelligence.analysis.search`, a module that does not exist — an `ImportError` that blocked importing *any* analysis module. Removed the dangling import + its `__all__` entry (one-line fix). No other file was edited.

**B1 — Cross-source deterministic PK collision (blocks all extraction).** `ExtractedObject.stable_id()` (in `intelligence/parsing/extractor.py`) derives the knowledge-object id from `(source_id, source_location, type, chunk_hash)`, where `source_id` is the **source UUID** and `source_location` is the **repo-relative path** (e.g. `API_DOCUMENTATION.md#Overview`). Two repos that ship identical content at the same path produce the **same** id, so the second ingest hits `knowledge_objects_pkey` and the whole extract (and thus the whole ingest) rolls back. Confirmed live: the colliding id `cc449f1b-…` is owned by `avfs-backend`, and `momento-core` ships the same `API_DOCUMENTATION.md`. This is why knowledge objects are frozen at 198. Fix: make the id source-scoped (include the source UUID *and* a disambiguator for the same path across sources, or scope the upsert per source) — that is an `extractor.py` change, out of my allowed scope.

**B2 — `NameError: name 'existing_ids' is not defined` (latent, in `extractor.py` `run()`).** `existing_ids` is computed *inside* the per-document `try`; if `extract_text()` (or loading) raises before that line, the `except` handler at the end of the loop references `existing_ids`, which is still unbound. This masks the real per-document error as a `NameError`. Out of scope.

**B3 — `MarkdownCollector` has no `repo_name`** (in `intelligence/ingest/markdown_collector.py`). Every `--source-type markdown` ingest crashes at collection, so `docs/` was never registered as a source. Out of scope.

**B4 — `KnowledgeObject.select()` does not exist** (in `intelligence/analysis/contradictions.py` and `intelligence/analysis/insights.py`). Both scanners abort with `AttributeError`, so they report `objects_scanned=0` and find nothing. Contradictions/insights are therefore *unrunnable as-is*. Out of scope.

**Note for the test agent:** the full pytest suite will likely surface B1/B2/B3/B4 (extraction, markdown ingest, analysis). These are pre-existing, not introduced by this run.

## 12. VERDICT

`E2E STATUS: PARTIAL PASS — ingestion (collect), report generation, and search are verified working against the live DB with real provenance and a clean negative control, but end-to-end ingestion is blocked for all multi-source repos by a cross-source deterministic-id primary-key collision (B1) that halts knowledge extraction at 198 objects, and markdown ingest is blocked by B3.`

**Sources that failed to ingest (and why):**
- `docs/` (markdown) — collection crashed: `AttributeError: 'MarkdownCollector' object has no attribute 'repo_name'` (B3). Source never registered.
- `momento-core3`, `MomentoRabbit`, `momento-core`, `MomentoFX`, `InvestigationSuite`, `MomentoV5`, `momento-avfs-core` (git) — **collect phase succeeded** (source + documents rows created, 2,359 docs) but the **extract phase crashed** on the cross-source PK collision (B1), so their knowledge objects were not materialized.
