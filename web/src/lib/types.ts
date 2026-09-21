/**
 * Shared API types for the MKC dashboard.
 *
 * These types mirror the *current* backend contract (backend/src/mkc): the
 * models' to_dict() output, the PagedResponse envelope, and the detailed
 * error payload ({"detail": {"code", "detail", ...extra}}).
 *
 * `src/lib/api.ts` is the only file that talks to the network. When the
 * contract drifts, only types.ts + api.ts (and the mock.ts shapes) change.
 */

// ---------------------------------------------------------------------------
// Provenance
// ---------------------------------------------------------------------------

/** Immutable provenance record as stored in knowledge_objects.provenance.
 *  Keys vary by extraction pipeline, so everything is optional and unknown
 *  keys are tolerated. */
export interface Provenance {
  source_type?: string
  source_id?: string
  /** Backend key for "where in the source" (repo path / line range / message id). */
  source_location?: string
  /** Some pipelines use file_path instead of source_location. */
  file_path?: string
  commit_hash?: string
  /** Some pipelines record the commit under `commit`. */
  commit?: string
  author?: string
  date?: string | null
  extraction_method?: string
  original_text?: string
  [key: string]: unknown
}

/** Provenance with the UI canonical fields resolved (aliases flattened). */
export interface ProvenanceView {
  source_type?: string
  source_id?: string
  file_path?: string
  commit_hash?: string
  author?: string
  date?: string | null
  extraction_method?: string
  original_text?: string
}

export function toProvenanceView(p: Provenance | null | undefined): ProvenanceView {
  if (!p) return {}
  const asString = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined)
  return {
    source_type: asString(p.source_type),
    source_id: asString(p.source_id),
    file_path: asString(p.file_path) ?? asString(p.source_location),
    commit_hash: asString(p.commit_hash) ?? asString(p.commit),
    author: asString(p.author),
    date: asString(p.date) ?? null,
    extraction_method: asString(p.extraction_method),
    original_text: asString(p.original_text),
  }
}

// ---------------------------------------------------------------------------
// Knowledge
// ---------------------------------------------------------------------------

export interface Source {
  id: string
  source_type: string
  source_id: string
  path: string
  metadata_json: Record<string, unknown>
  indexed_at: string | null
}

export interface KnowledgeObject {
  id: string
  type: string
  title: string
  content_summary: string
  body: string
  lifecycle_state: string
  confidence: number
  source_id: string | null
  provenance: Provenance
  status: string
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeDetail extends KnowledgeObject {
  source?: Source | null
  provenance_chain?: { object: Provenance; source: Source | null } | null
}

/** A typed edge resolved against the current object (direction from its POV). */
export interface KnowledgeRelation {
  id: string
  direction: 'out' | 'in'
  rel_type: string
  other_id: string
  other_type?: string
  other_title?: string
  confidence?: number
  reason?: string
}

// ---------------------------------------------------------------------------
// Audit / status
// ---------------------------------------------------------------------------

export interface AuditEntry {
  id: string
  action: string
  actor: string
  object_type: string
  object_id: string
  details: Record<string, unknown>
  at: string | null
}

/** Response of GET /api/v1/status (the registry summary surface). */
export interface StatusSummary {
  version: string
  knowledge_objects_total: number
  by_type: Record<string, number>
  by_lifecycle_state: Record<string, number>
  recent_activity: AuditEntry[]
  /** Optional surfaces the backend may add; shown when present. */
  documents?: number
  sources?: number
  last_ingest?: string | null
}

// ---------------------------------------------------------------------------
// Research
// ---------------------------------------------------------------------------

export interface ResearchItem {
  id: string
  knowledge_id: string
  title: string
  topic: string
  status: string
  hypothesis: string
  evidence_count: number
  validation_level: string
  related_modules: string[]
}

// ---------------------------------------------------------------------------
// Decisions
// ---------------------------------------------------------------------------

export interface Decision {
  id: string
  knowledge_id: string
  title: string
  context: string
  problem: string
  alternatives: string
  decision_text: string
  reason: string
  evidence: string
  affected_components: string[]
  status: string
  author: string
  decided_at: string | null
  /** Set when the supersede call named a replacement; the backend records the
   *  target in the audit trail, the API does not return it on the object. */
  superseded_by?: string | null
}

// ---------------------------------------------------------------------------
// Experiments
// ---------------------------------------------------------------------------

export interface Experiment {
  id: string
  knowledge_id: string
  title: string
  hypothesis_tested: string
  dataset: string
  method: string
  result: string
  statistics_json: Record<string, unknown>
  conclusion: string
  status: string
  reproducibility: string
  limitations: string
}

// ---------------------------------------------------------------------------
// Insights & contradictions
// ---------------------------------------------------------------------------

export interface Insight {
  id: string
  knowledge_ids: string[]
  insight_type: string
  summary: string
  supporting_evidence: string[]
  confidence: number
  status: string
  analysis_run?: string | null
}

export interface Contradiction {
  id: string
  claim_a_id: string
  claim_b_id: string
  severity: string
  status: string
  explanation: string
  resolved_by?: string
  claim_a_title?: string
  claim_b_title?: string
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface ReportMeta {
  id: string
  type: string
  path: string
  generated_at: string | null
  summary: string
}

// ---------------------------------------------------------------------------
// Health / metrics
// ---------------------------------------------------------------------------

export interface HealthStatus {
  status: string
  database: string
  version?: string
}

// ---------------------------------------------------------------------------
// Envelopes / errors / query params
// ---------------------------------------------------------------------------

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ApiErrorInfo {
  status: number
  code: string
  detail: string
  allowed_next_states?: string[]
}

export interface ListParams {
  page?: number
  page_size?: number
}

export interface KnowledgeQuery extends ListParams {
  type?: string
  lifecycle_state?: string
  q?: string
}

export interface ResourceQuery extends ListParams {
  status?: string
  knowledge_id?: string
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface ScoredKnowledge extends KnowledgeObject {
  /** 0 for live full-text results (the API returns no score), real value in
   *  mock mode. */
  score: number
  rank: number
}

export interface SearchResult {
  query: string
  total: number
  elapsed_ms: number
  items: ScoredKnowledge[]
}
