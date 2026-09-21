/**
 * Deterministic mock dataset for the MKC dashboard.
 *
 * Used automatically by src/lib/api.ts whenever the API is unreachable, the
 * token is missing/invalid, or mock mode is forced. Every record is invented
 * (the whole corpus describes the fictional "MKC project" managing its own
 * knowledge) and the UI shows a permanent banner while mock data is on
 * screen — this file must never be mistaken for live data.
 *
 * All members are synchronous: api.ts passes them to dataRequest as
 * `() => mockApi.x(query)`.
 */
import { ApiError } from './errors'
import type {
  AuditEntry,
  Contradiction,
  Decision,
  Experiment,
  HealthStatus,
  Insight,
  KnowledgeDetail,
  KnowledgeObject,
  KnowledgeQuery,
  Paged,
  Provenance,
  ReportMeta,
  ResearchItem,
  ResourceQuery,
  SearchResult,
  Source,
  StatusSummary,
} from './types'

export const MOCK_VERSION = '0.1.0'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function prov(source_type: string, source_id: string, extra: Partial<Provenance> = {}): Provenance {
  return { source_type, source_id, ...extra }
}

function paged<T>(items: T[], page: number | undefined, page_size: number | undefined): Paged<T> {
  const p = Math.max(1, page ?? 1)
  const size = Math.max(1, Math.min(100, page_size ?? 20))
  const start = (p - 1) * size
  return { items: items.slice(start, start + size), total: items.length, page: p, page_size: size }
}

function notFound(what: string, id: string): never {
  throw new ApiError({ status: 404, code: 'not_found', detail: `${what} not found: ${id}` })
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

const SOURCES: Source[] = [
  {
    id: 'src-git-mkc',
    source_type: 'git',
    source_id: 'mkc@main',
    path: 'repo:mkc',
    metadata_json: { url: 'git@localhost:mkc.git', branch: 'main', files: 214 },
    indexed_at: '2026-09-19T06:30:00Z',
  },
  {
    id: 'src-chatgpt-dedup',
    source_type: 'chatgpt',
    source_id: 'thread-88231',
    path: 'chatgpt:dedup-strategies',
    metadata_json: { model: 'gpt-4.1', messages: 42, topic: 'deduplication strategies' },
    indexed_at: '2026-09-16T14:02:00Z',
  },
  {
    id: 'src-commit-a1b2c3d',
    source_type: 'commit',
    source_id: 'a1b2c3d9e4f506781234567890abcdef12345678',
    path: 'commit:a1b2c3d9',
    metadata_json: { subject: 'storage: switch ingest path to WAL mode', date: '2026-09-14T09:11:00Z' },
    indexed_at: '2026-09-14T09:12:00Z',
  },
]

// ---------------------------------------------------------------------------
// Knowledge objects (one per used type; 34 total)
// ---------------------------------------------------------------------------

const KNOWLEDGE: KnowledgeObject[] = [
  // --- documents -----------------------------------------------------------
  {
    id: 'ko-mkc-arch',
    type: 'document',
    title: 'MKC architecture overview',
    content_summary: 'Registry, lifecycle, storage and ingest pipeline as shipped in v0.1.',
    body: 'MKC is a provenance-first knowledge registry. The registry owns objects and transitions; the ingest pipeline extracts claims from indexed sources; the storage layer persists everything in a single SQLite database with FTS5.',
    lifecycle_state: 'production',
    confidence: 0.97,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/architecture.md',
      commit_hash: 'a1b2c3d9e4f506781234567890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-12',
      extraction_method: 'document.parse',
      original_text: 'MKC is a provenance-first knowledge registry…',
    }),
    status: 'active',
    created_at: '2026-08-02T10:00:00Z',
    updated_at: '2026-09-12T08:15:00Z',
  },
  {
    id: 'ko-lifecycle-spec',
    type: 'document',
    title: 'Lifecycle transition specification',
    content_summary: 'The 15 states, the happy path, and the terminal exits.',
    body: 'Every knowledge object moves through 15 lifecycle states. The happy path runs idea → question → hypothesis → researching → experiment → observed → validating → validated → implemented → production. Terminal states (contradicted, rejected, deprecated, superseded) are absorbing.',
    lifecycle_state: 'implemented',
    confidence: 0.95,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/lifecycle.md',
      commit_hash: 'a1b2c3d9e4f506781234567890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-10',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-08-05T09:30:00Z',
    updated_at: '2026-09-10T12:00:00Z',
  },
  {
    id: 'ko-storage-design',
    type: 'document',
    title: 'SQLite storage design notes',
    content_summary: 'Schema layout, WAL choice, and the FTS5 side index.',
    body: 'Single database file, WAL mode enabled, one FTS5 virtual table over knowledge objects. Writes are serialized on the ingest process; reads are unbounded. Migrations run as ordered PRAGMA/DDL statements at startup.',
    lifecycle_state: 'validated',
    confidence: 0.9,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/storage.md',
      commit_hash: 'a1b2c3d9e4f506781234567890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-14',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-08-10T11:00:00Z',
    updated_at: '2026-09-14T09:11:00Z',
  },

  // --- sources -------------------------------------------------------------
  {
    id: 'ko-src-git',
    type: 'source',
    title: 'git: mkc repository',
    content_summary: 'Primary source: the mkc git repository (main branch).',
    body: '214 files indexed, last full ingest 2026-09-19. All document- and code-derived knowledge objects trace here unless they cite the research thread.',
    lifecycle_state: 'production',
    confidence: 0.99,
    source_id: 'src-git-mkc',
    provenance: prov('git', 'mkc@main', {
      file_path: 'repo:mkc',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-19',
      extraction_method: 'git.walk',
    }),
    status: 'active',
    created_at: '2026-08-02T10:05:00Z',
    updated_at: '2026-09-19T06:30:00Z',
  },
  {
    id: 'ko-src-chatgpt',
    type: 'source',
    title: 'chatgpt: research thread on deduplication',
    content_summary: '42-message thread comparing hash, embedding and FTS dedup approaches.',
    body: 'Research conversation used as the seed for the deduplication topic. Claims extracted from it are flagged with extraction_method chatgpt.extract and require validation before use.',
    lifecycle_state: 'production',
    confidence: 0.85,
    source_id: 'src-chatgpt-dedup',
    provenance: prov('chatgpt', 'thread-88231', {
      file_path: 'chatgpt:dedup-strategies',
      author: 'op:admin',
      date: '2026-09-16',
      extraction_method: 'chatgpt.extract',
      original_text: '…so embedding similarity >0.92 usually catches exact duplicates…',
    }),
    status: 'active',
    created_at: '2026-09-16T14:02:00Z',
    updated_at: '2026-09-16T14:02:00Z',
  },
  {
    id: 'ko-src-commit',
    type: 'source',
    title: 'commit: a1b2c3d (storage engine)',
    content_summary: 'Single commit: "storage: switch ingest path to WAL mode".',
    body: 'The commit that enabled WAL mode on the ingest path. Cited by the WAL safety claim and the concurrency experiment.',
    lifecycle_state: 'validated',
    confidence: 0.98,
    source_id: 'src-commit-a1b2c3d',
    provenance: prov('commit', 'a1b2c3d9e4f5067890abcdef12345678', {
      file_path: 'commit:a1b2c3d9',
      commit: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-14',
      extraction_method: 'commit.diff',
      original_text: 'storage: switch ingest path to WAL mode',
    }),
    status: 'active',
    created_at: '2026-09-14T09:12:00Z',
    updated_at: '2026-09-14T09:12:00Z',
  },

  // --- facts & claims -------------------------------------------------------
  {
    id: 'ko-fact-idx-perf',
    type: 'fact',
    title: 'FTS5 index build stays under 50 ms at 10k documents',
    content_summary: 'Measured during the 2026-09-08 full reindex.',
    body: 'A full FTS5 rebuild of the 10,000-document corpus took 41 ms median across 10 runs. Well inside the 50 ms budget for the ingest path.',
    lifecycle_state: 'validated',
    confidence: 0.96,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'bench/fts_index.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-08',
      extraction_method: 'benchmark.record',
    }),
    status: 'active',
    created_at: '2026-09-08T13:00:00Z',
    updated_at: '2026-09-09T08:00:00Z',
  },
  {
    id: 'ko-fact-wal-rollback',
    type: 'fact',
    title: 'WAL + busy_timeout caused intermittent rollbacks under 8 writers',
    content_summary: 'Observed in the 30-trial concurrency experiment.',
    body: 'With 8 concurrent writer processes and busy_timeout=5000 ms, 3 of 30 trials hit SQLITE_BUSY and rolled back the batch. The ingest path therefore keeps a single writer process.',
    lifecycle_state: 'contradicted',
    confidence: 0.9,
    source_id: 'src-commit-a1b2c3d',
    provenance: prov('research', 'ex-wal-concurrency', {
      file_path: 'bench/wal_concurrency.py',
      commit: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'pipeline:experiment',
      date: '2026-09-15',
      extraction_method: 'experiment.record',
      original_text: 'trial 17: SQLITE_BUSY (5) during commit',
    }),
    status: 'active',
    created_at: '2026-09-15T17:30:00Z',
    updated_at: '2026-09-17T10:00:00Z',
  },
  {
    id: 'ko-claim-wal-safe',
    type: 'claim',
    title: 'WAL mode is safe for concurrent reader/writer on the ingest path',
    content_summary: 'Held for 1 writer + N readers; the 8-writer case is the exception.',
    body: 'Under the single-writer ingest architecture, WAL mode shows no reader-visible anomalies across 30 trials. This claim stands for the 1-writer configuration only; the 8-writer fact (ko-fact-wal-rollback) contradicts it as stated.',
    lifecycle_state: 'validated',
    confidence: 0.88,
    source_id: 'src-commit-a1b2c3d',
    provenance: prov('research', 'ex-wal-concurrency', {
      file_path: 'bench/wal_concurrency.py',
      commit: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-15',
      extraction_method: 'claim.extract',
    }),
    status: 'active',
    created_at: '2026-09-15T18:00:00Z',
    updated_at: '2026-09-19T11:12:00Z',
  },
  {
    id: 'ko-claim-u61-sufficient',
    type: 'claim',
    title: 'unicode61 tokenizer is sufficient for code identifier search',
    content_summary: 'Backed by the tokenizer benchmark on the mkc corpus.',
    body: 'For the Python-heavy mkc corpus, unicode61 finds every identifier a developer searched for in the 500-query benchmark. Trigram adds 55% p95 latency for no observed recall gain.',
    lifecycle_state: 'validated',
    confidence: 0.86,
    source_id: 'src-git-mkc',
    provenance: prov('research', 'ex-fts-bench', {
      file_path: 'bench/fts_bench.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'pipeline:experiment',
      date: '2026-09-11',
      extraction_method: 'claim.extract',
      original_text: 'unicode61 recall 1.00 on the identifier set',
    }),
    status: 'active',
    created_at: '2026-09-11T16:00:00Z',
    updated_at: '2026-09-13T09:00:00Z',
  },
  {
    id: 'ko-claim-trigram-needed',
    type: 'claim',
    title: 'Trigram indexing is required for reliable substring matches on C++ identifiers',
    content_summary: 'Contradicts the unicode61-sufficiency claim on C++-heavy corpora.',
    body: 'Counterpoint from the C++ corpus sample: unicode61 misses camelCase substrings like "requestId" inside identifiers. If C++ corpora enter scope, trigram (or porter+trigram) is required.',
    lifecycle_state: 'researching',
    confidence: 0.61,
    source_id: 'src-chatgpt-dedup',
    provenance: prov('chatgpt', 'thread-88231', {
      file_path: 'chatgpt:dedup-strategies',
      author: 'op:admin',
      date: '2026-09-16',
      extraction_method: 'chatgpt.extract',
    }),
    status: 'active',
    created_at: '2026-09-16T14:20:00Z',
    updated_at: '2026-09-16T14:20:00Z',
  },

  // --- hypothesis / question -------------------------------------------------
  {
    id: 'ko-hyp-page-size',
    type: 'hypothesis',
    title: '8 KB page size beats 4 KB for knowledge rows',
    content_summary: 'Row width ~1.2 KB suggests 8 KB pages cut page faults.',
    body: 'Average knowledge row is 1.2 KB; 8 KB pages should hold ~6 rows versus ~3, halving page faults on full scans. Experiment ex-page-size is running.',
    lifecycle_state: 'hypothesis',
    confidence: 0.55,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'docs/storage.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-13',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-09-13T10:00:00Z',
    updated_at: '2026-09-13T10:00:00Z',
  },
  {
    id: 'ko-hyp-embed-dedup',
    type: 'hypothesis',
    title: 'Embedding similarity >0.92 identifies duplicate knowledge objects',
    content_summary: 'Rejected after the threshold sweep scored F1 0.61.',
    body: 'Proposed from the research thread. The sweep experiment (ex-embed-dedup) failed to hit the 0.80 F1 bar at any threshold, so the hypothesis was rejected in favour of exact-content hashing for v1.',
    lifecycle_state: 'rejected',
    confidence: 0.4,
    source_id: 'src-chatgpt-dedup',
    provenance: prov('chatgpt', 'thread-88231', {
      file_path: 'chatgpt:dedup-strategies',
      author: 'op:admin',
      date: '2026-09-16',
      extraction_method: 'chatgpt.extract',
    }),
    status: 'active',
    created_at: '2026-09-16T14:30:00Z',
    updated_at: '2026-09-19T16:40:00Z',
  },
  {
    id: 'ko-q-dedup',
    type: 'question',
    title: 'How should deduplication handle near-duplicate summaries?',
    content_summary: 'Exact hashing catches copies; paraphrases are still open.',
    body: 'Exact content hashing is in. Paraphrased summaries (same claim, different wording) are not deduplicated. Options on the table: canonical rewrites, clustering, or manual review queue.',
    lifecycle_state: 'question',
    confidence: 0.7,
    source_id: 'src-chatgpt-dedup',
    provenance: prov('chatgpt', 'thread-88231', {
      file_path: 'chatgpt:dedup-strategies',
      author: 'op:admin',
      date: '2026-09-16',
      extraction_method: 'chatgpt.extract',
    }),
    status: 'active',
    created_at: '2026-09-16T14:10:00Z',
    updated_at: '2026-09-16T14:10:00Z',
  },

  // --- insight / experiments (knowledge type) --------------------------------
  {
    id: 'ko-ins-density',
    type: 'insight',
    title: 'Validated claims cluster around storage and ingest',
    content_summary: '61% of validated objects touch mkc.store or the ingest pipeline.',
    body: 'Across the registry, validated claims and facts concentrate on the storage/ingest subsystems, matching where the most experiments have been run. Core registry code has thinner evidence than its surface area suggests.',
    lifecycle_state: 'observed',
    confidence: 0.82,
    source_id: 'src-git-mkc',
    provenance: prov('research', 'ins-analysis', {
      file_path: 'analysis/2026-09-18/density.json',
      author: 'system:analyst',
      date: '2026-09-18',
      extraction_method: 'analysis.run',
    }),
    status: 'active',
    created_at: '2026-09-18T09:00:00Z',
    updated_at: '2026-09-18T09:00:00Z',
  },
  {
    id: 'ko-ex-fts-bench',
    type: 'experiment',
    title: 'FTS5 tokenizer comparison: unicode61 vs trigram',
    content_summary: '500-query benchmark, 10k docs, p95 latency and recall.',
    body: 'Compared unicode61 and trigram tokenizers on the mkc corpus. unicode61: p95 3.8 ms, recall 1.00 on the identifier set. trigram: p95 5.9 ms, recall 1.00. Result supported the unicode61 claim and the search decision.',
    lifecycle_state: 'experiment',
    confidence: 0.93,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'bench/fts_bench.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'pipeline:experiment',
      date: '2026-09-11',
      extraction_method: 'experiment.record',
    }),
    status: 'active',
    created_at: '2026-09-11T09:00:00Z',
    updated_at: '2026-09-12T18:00:00Z',
  },
  {
    id: 'ko-ex-embed',
    type: 'experiment',
    title: 'Embedding similarity threshold sweep for dedup',
    content_summary: 'Swept 0.80–0.99; best F1 0.61 — below bar, experiment failed.',
    body: '500 sampled document pairs, cosine similarity sweep from 0.80 to 0.99. Best F1 was 0.61 at threshold 0.92, far below the 0.80 acceptance bar. The hypothesis was rejected; the experiment is recorded as FAILED with its full statistics.',
    lifecycle_state: 'rejected',
    confidence: 0.9,
    source_id: 'src-chatgpt-dedup',
    provenance: prov('research', 'ex-embed-dedup', {
      file_path: 'bench/embed_sweep.py',
      author: 'pipeline:experiment',
      date: '2026-09-19',
      extraction_method: 'experiment.record',
    }),
    status: 'active',
    created_at: '2026-09-17T10:00:00Z',
    updated_at: '2026-09-19T16:40:00Z',
  },

  // --- decisions (knowledge type) --------------------------------------------
  {
    id: 'ko-dec-sqlite',
    type: 'decision',
    title: 'Decision: adopt SQLite as the single storage engine',
    content_summary: 'One file, one FTS index; no external DB for v1.',
    body: 'Recorded 2026-08-15. SQLite chosen over Postgres/SQLite+pgvector: the corpus is single-node and read-heavy; an embedded engine removes the ops surface. Supersedes the earlier "Postgres for v1" draft.',
    lifecycle_state: 'production',
    confidence: 0.97,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/decisions/sqlite.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-08-15',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-08-15T15:00:00Z',
    updated_at: '2026-09-01T09:00:00Z',
  },
  {
    id: 'ko-dec-fts',
    type: 'decision',
    title: 'Decision: use FTS5 unicode61 for full-text search',
    content_summary: 'Backed by the tokenizer benchmark; trigram deferred.',
    body: 'Recorded 2026-09-12 after ex-fts-bench validated the unicode61-sufficiency claim. Trigram remains a documented fallback for C++-heavy corpora.',
    lifecycle_state: 'implemented',
    confidence: 0.92,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/decisions/fts5.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-12',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-09-12T17:00:00Z',
    updated_at: '2026-09-12T17:00:00Z',
  },
  {
    id: 'ko-dec-batch-256',
    type: 'decision',
    title: 'Decision: batch ingest in 256-document chunks',
    content_summary: 'Superseded by the 1024-chunk decision.',
    body: 'Original ingest batching at 256 docs per transaction. Superseded 2026-09-18 by the 1024-chunk decision after throughput testing showed WAL writes dominate at small batch sizes.',
    lifecycle_state: 'superseded',
    confidence: 0.8,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/decisions/ingest-batch-256.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-08-20',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-08-20T11:00:00Z',
    updated_at: '2026-09-18T15:47:00Z',
  },
  {
    id: 'ko-dec-batch-1024',
    type: 'decision',
    title: 'Decision: batch ingest in 1024-document chunks',
    content_summary: 'Supersedes the 256-chunk decision; halves ingest wall time.',
    body: 'With 1024-doc transactions, a 10k-doc ingest dropped from 41 s to 19 s on the reference box. Memory stays bounded at ~28 MB per batch. Supersedes dc-batch-256.',
    lifecycle_state: 'implemented',
    confidence: 0.9,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/decisions/ingest-batch-1024.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-18',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-09-18T15:47:00Z',
    updated_at: '2026-09-18T15:47:00Z',
  },

  // --- modules / dependencies -------------------------------------------------
  {
    id: 'ko-mod-core',
    type: 'module',
    title: 'mkc.core — registry, lifecycle, constants',
    content_summary: 'Object store, transition table, and the 31-type vocabulary.',
    body: 'The registry core: knowledge object CRUD, lifecycle transition enforcement, and the constants that define types, states and allowed transitions.',
    lifecycle_state: 'production',
    confidence: 0.95,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'src/mkc/core/__init__.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-12',
      extraction_method: 'code.parse',
    }),
    status: 'active',
    created_at: '2026-08-02T10:10:00Z',
    updated_at: '2026-09-12T08:15:00Z',
  },
  {
    id: 'ko-mod-store',
    type: 'module',
    title: 'mkc.store — SQLite persistence',
    content_summary: 'Schema, migrations, WAL config, FTS5 side table.',
    body: 'Persistence layer: ordered migrations at startup, WAL mode, single-writer guarantee for the ingest path, and the FTS5 virtual table kept in sync by triggers.',
    lifecycle_state: 'implemented',
    confidence: 0.93,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'src/mkc/store/__init__.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-14',
      extraction_method: 'code.parse',
    }),
    status: 'active',
    created_at: '2026-08-10T11:30:00Z',
    updated_at: '2026-09-14T09:11:00Z',
  },
  {
    id: 'ko-dep-sqlite',
    type: 'dependency',
    title: 'sqlite3 (Python stdlib, system SQLite ≥3.43)',
    content_summary: 'FTS5 + trigram tokenizer require 3.43+; pinned in CI.',
    body: 'System SQLite via the stdlib sqlite3 module. CI pins 3.43+ because the trigram tokenizer (used only in benchmarks) needs it. No other runtime database dependency.',
    lifecycle_state: 'production',
    confidence: 0.96,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'pyproject.toml',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-08-15',
      extraction_method: 'manifest.parse',
    }),
    status: 'active',
    created_at: '2026-08-15T15:10:00Z',
    updated_at: '2026-08-15T15:10:00Z',
  },
  {
    id: 'ko-dep-uv',
    type: 'dependency',
    title: 'uv (package manager)',
    content_summary: 'Dropped in favour of pip-tools; kept for lockfile migration.',
    body: 'uv was the dev environment manager until 2026-09-05, when the project moved to pip-tools + requirements.lock. The dependency is deprecated; a migration note remains for contributors with old checkouts.',
    lifecycle_state: 'deprecated',
    confidence: 0.9,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/decisions/pip-tools.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-05',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-07-20T09:00:00Z',
    updated_at: '2026-09-05T12:00:00Z',
  },

  // --- engineering knowledge ---------------------------------------------------
  {
    id: 'ko-req-99pct',
    type: 'requirement',
    title: '99% of lookups under 100 ms at 100k objects',
    content_summary: 'Non-negotiable performance requirement for v1.',
    body: 'The registry must serve 99% of object lookups in under 100 ms once the corpus reaches 100k objects. Current state at 34 objects: p95 1.9 ms (ko-metric-lookup).',
    lifecycle_state: 'implemented',
    confidence: 0.99,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/requirements.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-08-01',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-08-01T09:00:00Z',
    updated_at: '2026-09-01T09:00:00Z',
  },
  {
    id: 'ko-bench-fts',
    type: 'benchmark',
    title: 'FTS5 p95 query latency (10k docs)',
    content_summary: '3.8 ms p95 with unicode61; 5.9 ms with trigram.',
    body: '500-query benchmark, 10k documents: unicode61 p95 3.8 ms, p99 6.1 ms; trigram p95 5.9 ms, p99 9.4 ms. Re-run on every release candidate.',
    lifecycle_state: 'observed',
    confidence: 0.94,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'bench/fts_bench.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'pipeline:experiment',
      date: '2026-09-11',
      extraction_method: 'benchmark.record',
    }),
    status: 'active',
    created_at: '2026-09-11T16:00:00Z',
    updated_at: '2026-09-12T18:00:00Z',
  },
  {
    id: 'ko-risk-corruption',
    type: 'risk',
    title: 'SQLite file corruption from power loss mid-write',
    content_summary: 'WAL mitigates but does not eliminate; no validated recovery evidence yet.',
    body: 'A power loss during a checkpoint could still corrupt the WAL. Mitigations considered: periodic backups, integrity_check on start. No experiment has validated a recovery procedure, so this stays at researching with an open evidence gap.',
    lifecycle_state: 'researching',
    confidence: 0.75,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/risks.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-17',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-09-17T10:03:00Z',
    updated_at: '2026-09-17T10:03:00Z',
  },
  {
    id: 'ko-debt-migrations',
    type: 'tech_debt',
    title: 'Schema migrations are ad-hoc PRAGMA-based',
    content_summary: 'No versioned migration table; repeatable runs are a TODO.',
    body: 'Migrations run by scanning DDL statements without a schema_version table. Works while the team is one; the first multi-developer change will need a proper migration ledger.',
    lifecycle_state: 'hypothesis',
    confidence: 0.6,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'src/mkc/store/migrate.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-08',
      extraction_method: 'code.parse',
    }),
    status: 'active',
    created_at: '2026-09-08T14:00:00Z',
    updated_at: '2026-09-08T14:00:00Z',
  },
  {
    id: 'ko-plan-q4',
    type: 'plan',
    title: 'Q4 plan: research pipeline GA',
    content_summary: 'Ship the research → experiment → insight loop without flags.',
    body: 'Q4 goals: research pipeline out of feature-flag, contradiction review workflow in the dashboard, and the first 100k-object scale run. Depends on the durability evidence gap closing.',
    lifecycle_state: 'validated',
    confidence: 0.85,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/plans/q4.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-15',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-09-15T09:00:00Z',
    updated_at: '2026-09-19T08:00:00Z',
  },

  // --- people / projects / measurement ------------------------------------------
  {
    id: 'ko-proj-mkc',
    type: 'project',
    title: 'MKC — Momento Knowledge Core',
    content_summary: 'The registry this dashboard shows.',
    body: 'Provenance-first knowledge registry for the Momento workbench. Single-operator for v1, localhost-first, REST API over SQLite.',
    lifecycle_state: 'production',
    confidence: 0.99,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'README.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-08-02',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-07-20T09:00:00Z',
    updated_at: '2026-09-12T08:15:00Z',
  },
  {
    id: 'ko-sub-registry',
    type: 'subsystem',
    title: 'Registry subsystem',
    content_summary: 'Objects, transitions, relations — the heart of MKC.',
    body: 'The registry owns the 31 knowledge types, the 15-state lifecycle, and typed edges between objects. All other subsystems (ingest, analysis, reporting) read from or write through it.',
    lifecycle_state: 'production',
    confidence: 0.97,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'src/mkc/core/registry.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-12',
      extraction_method: 'code.parse',
    }),
    status: 'active',
    created_at: '2026-08-02T10:10:00Z',
    updated_at: '2026-09-12T08:15:00Z',
  },
  {
    id: 'ko-metric-lookup',
    type: 'metric',
    title: 'lookup_p95_ms',
    content_summary: 'p95 registry lookup latency; 1.9 ms at 34 objects.',
    body: 'Prometheus histogram mkc_lookup_seconds, p95 bucket. Currently 1.9 ms at the 34-object corpus; tracked against the 100 ms @ 100k requirement (ko-req-99pct).',
    lifecycle_state: 'observed',
    confidence: 0.95,
    source_id: 'src-git-mkc',
    provenance: prov('code', 'mkc@main', {
      file_path: 'src/mkc/api/metrics.py',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-09-06',
      extraction_method: 'metric.record',
    }),
    status: 'active',
    created_at: '2026-09-06T10:00:00Z',
    updated_at: '2026-09-19T06:30:00Z',
  },
  {
    id: 'ko-person-ada',
    type: 'person',
    title: 'Ada Lovelace (operator)',
    content_summary: 'Primary operator; author of most recorded decisions.',
    body: 'Single operator of the MKC instance (op:admin in the audit trail). Records decisions and reviews insights.',
    lifecycle_state: 'production',
    confidence: 0.9,
    source_id: 'src-git-mkc',
    provenance: prov('markdown', 'mkc@main', {
      file_path: 'docs/team.md',
      commit_hash: 'a1b2c3d9e4f5067890abcdef12345678',
      author: 'op:admin',
      date: '2026-08-02',
      extraction_method: 'document.parse',
    }),
    status: 'active',
    created_at: '2026-08-02T10:20:00Z',
    updated_at: '2026-08-02T10:20:00Z',
  },
]

// ---------------------------------------------------------------------------
// Research
// ---------------------------------------------------------------------------

const RESEARCH: ResearchItem[] = [
  {
    id: 'rs-dedup',
    knowledge_id: 'ko-q-dedup',
    title: 'Deduplication strategies for knowledge objects',
    topic: 'deduplication',
    status: 'running',
    hypothesis: 'Exact content hashing plus a manual review queue covers v1; embeddings are not worth the cost.',
    evidence_count: 7,
    validation_level: 'single-source',
    related_modules: ['mkc.core', 'mkc.ingest'],
  },
  {
    id: 'rs-tokenizer',
    knowledge_id: 'ko-claim-u61-sufficient',
    title: 'FTS5 tokenizer selection',
    topic: 'full-text search',
    status: 'validated',
    hypothesis: 'unicode61 matches trigram recall on the mkc corpus at 35% lower p95 latency.',
    evidence_count: 5,
    validation_level: 'reproduced',
    related_modules: ['mkc.store'],
  },
  {
    id: 'rs-storage',
    knowledge_id: 'ko-hyp-page-size',
    title: 'Storage engine scaling beyond 100k objects',
    topic: 'scaling',
    status: 'planned',
    hypothesis: 'Page-size tuning and covering indexes keep lookups under 100 ms p99 at 100k objects.',
    evidence_count: 0,
    validation_level: 'none',
    related_modules: ['mkc.store'],
  },
  {
    id: 'rs-embed',
    knowledge_id: 'ko-hyp-embed-dedup',
    title: 'Embedding-based retrieval and dedup',
    topic: 'semantic search',
    status: 'archived',
    hypothesis: 'Dense embeddings enable near-duplicate detection and semantic search.',
    evidence_count: 12,
    validation_level: 'reproduced',
    related_modules: ['mkc.core'],
  },
]

// ---------------------------------------------------------------------------
// Decisions
// ---------------------------------------------------------------------------

const DECISIONS: Decision[] = [
  {
    id: 'dc-sqlite',
    knowledge_id: 'ko-dec-sqlite',
    title: 'Adopt SQLite as the single storage engine',
    context: 'v1 architecture: the registry needed a storage engine with full-text search, single-node operation, and zero external services.',
    problem: 'Postgres offered FTS but added an ops dependency (server, auth, backups) the single-operator deployment could not justify.',
    alternatives: 'PostgreSQL + pgvector; SQLite with FTS5; LMDB custom schema. Postgres rejected on ops surface; LMDB rejected on missing FTS.',
    decision_text: 'Use a single SQLite database file with the FTS5 side index and WAL mode. No external database for v1.',
    reason: 'The corpus is read-heavy and single-node; an embedded engine removes the entire ops surface while FTS5 meets the search requirement (later validated by ex-fts-bench).',
    evidence: 'bench/fts_bench.py (10k docs, p95 3.8 ms); docs/requirements.md (no external services).',
    affected_components: ['mkc.store', 'mkc.ingest'],
    status: 'implemented',
    author: 'op:admin',
    decided_at: '2026-08-15T15:00:00Z',
    superseded_by: null,
  },
  {
    id: 'dc-fts',
    knowledge_id: 'ko-dec-fts',
    title: 'Use FTS5 unicode61 for full-text search',
    context: 'The search decision followed the tokenizer benchmark on the mkc corpus.',
    problem: 'Trigram indexing buys substring recall at +55% p95 latency and 2x index size; unclear whether the mkc corpus needs it.',
    alternatives: 'unicode61; trigram; porter + unicode61. Porter rejected (mangles code identifiers); trigram deferred.',
    decision_text: 'Ship FTS5 with the unicode61 tokenizer; document trigram as the fallback for C++-heavy corpora.',
    reason: 'ex-fts-bench showed recall parity (1.00 on the identifier set) at 35% lower p95; the unicode61-sufficiency claim was validated.',
    evidence: 'bench/fts_bench.py; ko-claim-u61-sufficient; ko-bench-fts.',
    affected_components: ['mkc.store'],
    status: 'accepted',
    author: 'op:admin',
    decided_at: '2026-09-12T17:00:00Z',
    superseded_by: null,
  },
  {
    id: 'dc-batch-256',
    knowledge_id: 'ko-dec-batch-256',
    title: 'Batch ingest in 256-document chunks',
    context: 'Ingest throughput on the reference box: 41 s per 10k documents.',
    problem: 'Small transactions meant WAL fsync overhead dominated ingest wall time.',
    alternatives: '256-doc transactions (original); 1024-doc transactions; per-document autocommit (rejected — 3x slower).',
    decision_text: 'Ingest writes in 256-document transactions.',
    reason: '256 was a conservative starting point to bound rollback scope before the WAL concurrency data landed.',
    evidence: 'bench/ingest_throughput.py (first run).',
    affected_components: ['mkc.ingest'],
    status: 'superseded',
    author: 'op:admin',
    decided_at: '2026-08-20T11:00:00Z',
    superseded_by: 'dc-batch-1024',
  },
  {
    id: 'dc-batch-1024',
    knowledge_id: 'ko-dec-batch-1024',
    title: 'Batch ingest in 1024-document chunks',
    context: 'Supersedes dc-batch-256 after the 2026-09-18 throughput re-test.',
    problem: 'Ingest wall time still dominated by commit frequency; rollback scope at 256 was never the binding constraint (WAL bounds it).',
    alternatives: 'Keep 256; move to 1024; make batch size a runtime flag (rejected — YAGNI for v1).',
    decision_text: 'Ingest writes in 1024-document transactions; memory stays bounded at ~28 MB per batch.',
    reason: '10k-doc ingest dropped from 41 s to 19 s; rollback behaviour unchanged under the single-writer guarantee (ex-wal-concurrency).',
    evidence: 'bench/ingest_throughput.py (2026-09-18 run); ex-wal-concurrency; ko-fact-wal-rollback (writer count kept at 1).',
    affected_components: ['mkc.ingest'],
    status: 'implemented',
    author: 'op:admin',
    decided_at: '2026-09-18T15:47:00Z',
    superseded_by: null,
  },
]

// ---------------------------------------------------------------------------
// Experiments (a FAILED experiment is first-class data, not an edge case)
// ---------------------------------------------------------------------------

const EXPERIMENTS: Experiment[] = [
  {
    id: 'ex-fts-bench',
    knowledge_id: 'ko-ex-fts-bench',
    title: 'FTS5 tokenizer comparison: unicode61 vs trigram',
    hypothesis_tested: 'unicode61 matches trigram recall on the mkc corpus at materially lower p95 latency.',
    dataset: '10,000 documents from the mkc corpus (seeded split)',
    method: '500 fixed queries (identifiers + natural language), p95/p99 latency and recall, 10 runs per configuration.',
    result: 'unicode61 p95 3.8 ms / p99 6.1 ms, recall 1.00. trigram p95 5.9 ms / p99 9.4 ms, recall 1.00. Index size 2x for trigram.',
    statistics_json: {
      doc_count: 10000,
      queries: 500,
      p95_unicode61_ms: 3.8,
      p99_unicode61_ms: 6.1,
      p95_trigram_ms: 5.9,
      p99_trigram_ms: 9.4,
      recall: { unicode61: 1.0, trigram: 1.0 },
      index_size_ratio_trigram: 2.1,
    },
    conclusion: 'Hypothesis confirmed. unicode61 adopted (dc-fts); trigram kept as the documented fallback for C++-heavy corpora.',
    status: 'validated',
    reproducibility: 'high — bench/fts_bench.py, fixed seed, pinned SQLite 3.45',
    limitations: 'Corpus is Python-heavy; the C++ substring case is covered only by the counter-claim ko-claim-trigram-needed.',
  },
  {
    id: 'ex-embed-dedup',
    knowledge_id: 'ko-ex-embed',
    title: 'Embedding similarity threshold sweep for dedup',
    hypothesis_tested: 'Cosine similarity >0.92 identifies duplicate knowledge objects at F1 ≥ 0.80.',
    dataset: '500 sampled document pairs (250 duplicates, 250 distinct)',
    method: 'Cosine similarity sweep from 0.80 to 0.99 in 0.01 steps; precision/recall per threshold.',
    result: 'Best F1 0.61 at threshold 0.92 — far below the 0.80 bar. Threshold performance unstable across languages.',
    statistics_json: {
      pairs: 500,
      best_f1: 0.61,
      best_threshold: 0.92,
      f1_at_092: 0.61,
      f1_at_095: 0.48,
      model: 'all-MiniLM-L6-v2 (CPU)',
    },
    conclusion: 'Hypothesis rejected. Exact content hashing retained for v1 dedup; semantic dedup deferred (rs-embed archived).',
    status: 'failed',
    reproducibility: 'medium — embeddings cached, model pinned, pair sampling script kept',
    limitations: 'Small pair sample; CPU-only inference; the duplicate set is hand-curated and may understate real-world duplication.',
  },
  {
    id: 'ex-page-size',
    knowledge_id: 'ko-hyp-page-size',
    title: '8 KB vs 4 KB SQLite page size',
    hypothesis_tested: '8 KB pages halve page faults on full scans of knowledge rows (~1.2 KB each).',
    dataset: '100k synthetic objects, schema identical to production',
    method: 'Full-scan and point-lookup workloads, 4 KB vs 8 KB, 5 runs each.',
    result: 'In progress — 8 KB shows +12% read throughput so far; write cost measurement pending.',
    statistics_json: { progress: 0.4, read_throughput_delta_pct: 12, runs_complete: 2, runs_total: 5 },
    conclusion: 'Pending. Decision will update ko-hyp-page-size and feed rs-storage.',
    status: 'running',
    reproducibility: 'planned — script in bench/page_size.py, not yet committed',
    limitations: 'Synthetic row distribution may not match the real corpus.',
  },
  {
    id: 'ex-wal-concurrency',
    knowledge_id: 'ko-fact-wal-rollback',
    title: 'WAL mode under concurrent writers',
    hypothesis_tested: 'WAL mode tolerates 8 concurrent writer processes with busy_timeout=5000 ms.',
    dataset: '30 trials, 8 writer processes, 500 writes each, shared DB file',
    method: 'Fixed write workload; count SQLITE_BUSY rollbacks per trial.',
    result: '3 of 30 trials rolled back on SQLITE_BUSY. 1-writer configuration showed zero anomalies across 30 trials.',
    statistics_json: { trials: 30, writers: 8, rollbacks: 3, single_writer_rollbacks: 0, busy_timeout_ms: 5000 },
    conclusion: 'WAL retained for the 1-writer ingest path; the 8-writer claim is contradicted and recorded (ko-fact-wal-rollback, cd-wal).',
    status: 'succeeded',
    reproducibility: 'high — bench/wal_concurrency.py, pinned SQLite 3.45',
    limitations: 'Local SSD only; network-attached storage may behave differently.',
  },
]

// ---------------------------------------------------------------------------
// Insights & contradictions
// ---------------------------------------------------------------------------

const INSIGHTS: Insight[] = [
  {
    id: 'ins-pattern',
    knowledge_ids: ['ko-mod-core', 'ko-mod-store', 'ko-fact-idx-perf'],
    insight_type: 'pattern',
    summary: 'Validated claims cluster around storage and ingest: 61% of validated objects touch mkc.store or the ingest pipeline.',
    supporting_evidence: [
      'ko-fact-idx-perf (validated 2026-09-09) and ko-claim-u61-sufficient (validated 2026-09-13) both concern mkc.store',
      '4 of 4 completed experiments targeted storage/ingest',
      'mkc.core has 10 active objects but only 2 validated claims',
    ],
    confidence: 0.82,
    status: 'accepted',
    analysis_run: 'run-2026-09-18',
  },
  {
    id: 'ins-gap',
    knowledge_ids: ['ko-risk-corruption', 'ko-debt-migrations'],
    insight_type: 'gap',
    summary: 'No validated evidence exists yet for durability under power loss or a repeatable schema migration path — both gate the Q4 plan.',
    supporting_evidence: [
      'ko-risk-corruption is at researching with 0 experiments attached',
      'ko-debt-migrations notes the missing schema_version table',
      'ko-plan-q4 lists durability evidence as a prerequisite',
    ],
    confidence: 0.74,
    status: 'needs_review',
    analysis_run: 'run-2026-09-18',
  },
  {
    id: 'ins-trend',
    knowledge_ids: ['ko-ex-fts-bench', 'ko-bench-fts', 'ko-metric-lookup'],
    insight_type: 'trend',
    summary: 'Lookup p95 has improved 38% across the last four ingest generations (3.1 ms → 1.9 ms).',
    supporting_evidence: [
      'lookup_p95_ms: 3.1 (08-20), 2.7 (09-01), 2.2 (09-12), 1.9 (09-19)',
      'Improvements coincide with the 1024-chunk decision and FTS5 trigger rewrite',
    ],
    confidence: 0.68,
    status: 'needs_review',
    analysis_run: 'run-2026-09-15',
  },
]

const CONTRADICTIONS: Contradiction[] = [
  {
    id: 'cd-wal',
    claim_a_id: 'ko-claim-wal-safe',
    claim_b_id: 'ko-fact-wal-rollback',
    severity: 'high',
    status: 'flagged',
    explanation:
      'ko-claim-wal-safe states WAL is safe for concurrent reader/writer traffic, but ex-wal-concurrency observed 3/30 rollbacks under 8 writers. The claim only holds for the single-writer configuration actually in use; the registry has flagged it pending a scope edit.',
    resolved_by: null,
    claim_a_title: 'WAL mode is safe for concurrent reader/writer on the ingest path',
    claim_b_title: 'WAL + busy_timeout caused intermittent rollbacks under 8 writers',
  },
  {
    id: 'cd-tokenizer',
    claim_a_id: 'ko-claim-u61-sufficient',
    claim_b_id: 'ko-claim-trigram-needed',
    severity: 'medium',
    status: 'resolved',
    explanation:
      'unicode61-sufficiency (validated on the mkc corpus) vs the trigram requirement on C++ identifiers. Resolved by scoping: v1 corpora are Python-only, so unicode61 stands; the trigram claim is retained as the trigger condition for revisiting dc-fts.',
    resolved_by: 'op:admin',
    claim_a_title: 'unicode61 tokenizer is sufficient for code identifier search',
    claim_b_title: 'Trigram indexing is required for reliable substring matches on C++ identifiers',
  },
]

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

const REPORTS: ReportMeta[] = [
  {
    id: 'rp-impl-plan-q4',
    type: 'implementation-plan',
    path: 'reports/2026-Q4/implementation-plan.md',
    generated_at: '2026-09-20T09:05:00Z',
    summary: 'Q4 implementation plan: research pipeline GA, contradiction review workflow, 100k-object scale run.',
  },
  {
    id: 'rp-project-knowledge-q3',
    type: 'project-knowledge',
    path: 'reports/2026-Q3/project-knowledge.md',
    generated_at: '2026-09-15T08:00:00Z',
    summary: 'End-of-Q3 state of the registry: 34 objects, 4 decisions, 4 experiments, evidence density by subsystem.',
  },
  {
    id: 'rp-research-gaps-q3',
    type: 'research-gaps',
    path: 'reports/2026-Q3/research-gaps.md',
    generated_at: '2026-09-15T08:10:00Z',
    summary: 'Open gaps: durability under power loss, semantic dedup (rejected in v1), C++ tokenizer recall, migration ledger.',
  },
  {
    id: 'rp-architecture-q3',
    type: 'architecture',
    path: 'reports/2026-Q3/architecture.md',
    generated_at: '2026-09-05T17:30:00Z',
    summary: 'Architecture report after the pip-tools switch: registry, ingest, storage and API surfaces with dependency map.',
  },
]

// ---------------------------------------------------------------------------
// Status / health / metrics
// ---------------------------------------------------------------------------

const ACTIVITY: AuditEntry[] = [
  {
    id: 'audit-101',
    action: 'contradiction.flag',
    actor: 'system:analyst',
    object_type: 'contradiction',
    object_id: 'cd-wal',
    details: { severity: 'high', claims: ['ko-claim-wal-safe', 'ko-fact-wal-rollback'] },
    at: '2026-09-20T18:22:00Z',
  },
  {
    id: 'audit-100',
    action: 'report.generate',
    actor: 'op:admin',
    object_type: 'report',
    object_id: 'rp-impl-plan-q4',
    details: { type: 'implementation-plan', path: 'reports/2026-Q4/implementation-plan.md' },
    at: '2026-09-20T09:05:00Z',
  },
  {
    id: 'audit-099',
    action: 'experiment.fail',
    actor: 'pipeline:experiment',
    object_type: 'experiment',
    object_id: 'ex-embed-dedup',
    details: { result: 'best_f1 0.61 < bar 0.80', hypothesis_id: 'ko-hyp-embed-dedup' },
    at: '2026-09-19T16:40:00Z',
  },
  {
    id: 'audit-098',
    action: 'lifecycle.transition',
    actor: 'op:admin',
    object_type: 'knowledge',
    object_id: 'ko-claim-wal-safe',
    details: { from: 'validating', to: 'validated' },
    at: '2026-09-19T11:12:00Z',
  },
  {
    id: 'audit-097',
    action: 'source.index',
    actor: 'pipeline:ingest',
    object_type: 'source',
    object_id: 'src-git-mkc',
    details: { documents: 214, mode: 'full' },
    at: '2026-09-19T06:30:00Z',
  },
  {
    id: 'audit-096',
    action: 'decision.record',
    actor: 'op:admin',
    object_type: 'decision',
    object_id: 'dc-batch-1024',
    details: { supersedes: 'dc-batch-256', status: 'implemented' },
    at: '2026-09-18T15:47:00Z',
  },
  {
    id: 'audit-095',
    action: 'knowledge.create',
    actor: 'pipeline:ingest',
    object_type: 'knowledge',
    object_id: 'ko-risk-corruption',
    details: { type: 'risk', lifecycle_state: 'researching' },
    at: '2026-09-17T10:03:00Z',
  },
  {
    id: 'audit-094',
    action: 'insight.accept',
    actor: 'op:admin',
    object_type: 'insight',
    object_id: 'ins-pattern',
    details: { insight_type: 'pattern' },
    at: '2026-09-16T13:29:00Z',
  },
]

function buildStatus(): StatusSummary {
  const by_type: Record<string, number> = {}
  const by_lifecycle_state: Record<string, number> = {}
  for (const ko of KNOWLEDGE) {
    by_type[ko.type] = (by_type[ko.type] ?? 0) + 1
    by_lifecycle_state[ko.lifecycle_state] = (by_lifecycle_state[ko.lifecycle_state] ?? 0) + 1
  }
  return {
    version: MOCK_VERSION,
    knowledge_objects_total: KNOWLEDGE.length,
    by_type,
    by_lifecycle_state,
    recent_activity: ACTIVITY,
    documents: 259,
    sources: SOURCES.length,
    last_ingest: '2026-09-19T06:30:00Z',
  }
}

const MOCK_STATUS = buildStatus()

const HEALTH: HealthStatus = { status: 'ok', database: 'ok', version: MOCK_VERSION }

const METRICS_TEXT = [
  '# HELP mkc_knowledge_objects_total Total knowledge objects in the registry',
  '# TYPE mkc_knowledge_objects_total gauge',
  `mkc_knowledge_objects_total ${KNOWLEDGE.length}`,
  '# HELP mkc_sources_total Indexed sources',
  '# TYPE mkc_sources_total gauge',
  `mkc_sources_total ${SOURCES.length}`,
  '# HELP mkc_documents_total Indexed documents',
  '# TYPE mkc_documents_total gauge',
  'mkc_documents_total 259',
  '# HELP mkc_contradictions_total Contradictions by status',
  '# TYPE mkc_contradictions_total gauge',
  `mkc_contradictions_total{status="flagged"} 1`,
  `mkc_contradictions_total{status="resolved"} 1`,
  '# HELP mkc_lookup_seconds Registry lookup latency histogram',
  '# TYPE mkc_lookup_seconds histogram',
  'mkc_lookup_seconds_bucket{le="0.005"} 498',
  'mkc_lookup_seconds_bucket{le="0.01"} 499',
  'mkc_lookup_seconds_bucket{le="+Inf"} 500',
  'mkc_lookup_seconds_sum 0.95',
  'mkc_lookup_seconds_count 500',
].join('\n')

// ---------------------------------------------------------------------------
// Query helpers
// ---------------------------------------------------------------------------

function filterKnowledge(query: KnowledgeQuery): KnowledgeObject[] {
  const q = (query.q ?? '').trim().toLowerCase()
  return KNOWLEDGE.filter((ko) => {
    if (query.type && ko.type !== query.type) return false
    if (query.lifecycle_state && ko.lifecycle_state !== query.lifecycle_state) return false
    if (q) {
      const hay = `${ko.title} ${ko.content_summary} ${ko.body}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

function filterResources<T extends { status: string; knowledge_id: string }>(
  all: T[],
  query: ResourceQuery,
): T[] {
  return all.filter((r) => {
    if (query.status && r.status !== query.status) return false
    if (query.knowledge_id && r.knowledge_id !== query.knowledge_id) return false
    return true
  })
}

function knowledgeDetail(id: string): KnowledgeDetail {
  const ko = KNOWLEDGE.find((k) => k.id === id)
  if (!ko) return notFound('Knowledge object', id)
  const source = ko.source_id ? (SOURCES.find((s) => s.id === ko.source_id) ?? null) : null
  return { ...ko, source, provenance_chain: { object: ko.provenance, source } }
}

/** Deterministic mock relevance: title > summary > body, plus type affinity. */
function searchScore(ko: KnowledgeObject, q: string): number {
  if (!q) return 0
  const needle = q.toLowerCase()
  let score = 0
  if (ko.title.toLowerCase().includes(needle)) score += 3
  if (ko.content_summary.toLowerCase().includes(needle)) score += 2
  const body = ko.body.toLowerCase()
  const hits = body.split(needle).length - 1
  score += Math.min(3, hits)
  if (ko.type === needle || ko.lifecycle_state === needle) score += 1
  return score
}

// ---------------------------------------------------------------------------
// The interface api.ts consumes
// ---------------------------------------------------------------------------

export const mockApi = {
  healthz(): HealthStatus {
    return HEALTH
  },

  metrics(): string {
    return METRICS_TEXT
  },

  status(): StatusSummary {
    return MOCK_STATUS
  },

  listKnowledge(query: KnowledgeQuery): Paged<KnowledgeObject> {
    return paged(filterKnowledge(query), query.page, query.page_size)
  },

  getKnowledge(id: string): KnowledgeDetail {
    return knowledgeDetail(id)
  },

  listResearch(query: ResourceQuery): Paged<ResearchItem> {
    return paged(filterResources(RESEARCH, query), query.page, query.page_size)
  },

  getResearch(id: string): ResearchItem {
    return RESEARCH.find((r) => r.id === id) ?? notFound('Research item', id)
  },

  listDecisions(query: ResourceQuery): Paged<Decision> {
    return paged(filterResources(DECISIONS, query), query.page, query.page_size)
  },

  getDecision(id: string): Decision {
    return DECISIONS.find((d) => d.id === id) ?? notFound('Decision', id)
  },

  listExperiments(query: ResourceQuery): Paged<Experiment> {
    return paged(filterResources(EXPERIMENTS, query), query.page, query.page_size)
  },

  getExperiment(id: string): Experiment {
    return EXPERIMENTS.find((e) => e.id === id) ?? notFound('Experiment', id)
  },

  listInsights(): Insight[] {
    return INSIGHTS
  },

  listContradictions(): Contradiction[] {
    return CONTRADICTIONS
  },

  listReports(): ReportMeta[] {
    return REPORTS
  },

  searchKnowledge(query: KnowledgeQuery): SearchResult {
    const matched = filterKnowledge(query).filter((ko) => searchScore(ko, query.q ?? '') > 0)
    const ranked = matched
      .map((ko) => ({ ...ko, score: searchScore(ko, query.q ?? '') }))
      .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title))
    const items = ranked.map((ko, i) => ({ ...ko, rank: i + 1 }))
    return {
      query: query.q ?? '',
      total: items.length,
      // Deterministic pseudo-latency: short queries are "fast", long ones slower.
      elapsed_ms: 4 + ((query.q?.length ?? 0) % 9),
      items,
    }
  },
}
