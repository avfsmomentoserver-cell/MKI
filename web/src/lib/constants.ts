/**
 * Domain vocabulary for the MKC dashboard.
 *
 * These values mirror `backend/src/mkc/core/constants.py` and the transition
 * table in `backend/src/mkc/core/lifecycle.py` (the authoritative sources —
 * keep in sync when the backend changes).
 */

/** The 31 knowledge object types (mirrors KNOWLEDGE_TYPES). */
export const KNOWLEDGE_TYPES = [
  // Ingested content
  'document',
  'source',
  'dataset',
  'glossary_term',
  // Claims about the world
  'fact',
  'claim',
  'hypothesis',
  'question',
  'theory',
  'observation',
  'insight',
  'research',
  'paper',
  'experiment',
  // Engineering knowledge
  'decision',
  'requirement',
  'module',
  'dependency',
  'implementation',
  'benchmark',
  'bug',
  'risk',
  'tech_debt',
  'plan',
  'task',
  'roadmap_item',
  // Measurement
  'metric',
  // People and projects
  'person',
  'project',
  'subsystem',
] as const

export type KnowledgeType = (typeof KNOWLEDGE_TYPES)[number]

/** All 15 lifecycle states (mirrors LIFECYCLE_STATES). */
export const LIFECYCLE_STATES = [
  'idea',
  'question',
  'hypothesis',
  'researching',
  'experiment',
  'observed',
  'validating',
  'validated',
  'implemented',
  'production',
  'contradicted',
  'rejected',
  'deprecated',
  'superseded',
  'unknown',
] as const

export type LifecycleState = (typeof LIFECYCLE_STATES)[number]

/** The canonical happy path, in order (mirrors HAPPY_PATH). */
export const HAPPY_PATH = [
  'idea',
  'question',
  'hypothesis',
  'researching',
  'experiment',
  'observed',
  'validating',
  'validated',
  'implemented',
  'production',
] as const

/** Terminal states are absorbing — no outgoing transitions. */
export const TERMINAL_STATES: ReadonlySet<string> = new Set([
  'contradicted',
  'rejected',
  'deprecated',
  'superseded',
])

/** States from which terminal exits are permitted (mirrors TERMINAL_FROM_STATES). */
const TERMINAL_FROM = new Set(['hypothesis', 'researching', 'experiment', 'observed', 'validating', 'validated'])

/**
 * Allowed transitions: current state -> reachable next states.
 * Mirrors LIFECYCLE_TRANSITIONS in backend/src/mkc/core/lifecycle.py.
 */
export function allowedNextStates(from: string): string[] {
  const idx = (HAPPY_PATH as readonly string[]).indexOf(from)
  const next: string[] = []
  if (idx >= 0 && idx + 1 < HAPPY_PATH.length) next.push(HAPPY_PATH[idx + 1])
  if (TERMINAL_FROM.has(from)) next.push('contradicted', 'deprecated', 'rejected', 'superseded')
  if (from === 'unknown') next.push(...(HAPPY_PATH as readonly string[]))
  if (TERMINAL_STATES.has(from) || idx === -1) return []
  return [...new Set(next)].sort()
}

/** Research / experiment workflow states (mirrors RESEARCH_STATUSES). */
export const RESEARCH_STATUSES = [
  'planned',
  'running',
  'paused',
  'failed',
  'succeeded',
  'validated',
  'archived',
] as const

export type ResearchStatus = (typeof RESEARCH_STATUSES)[number]

/** Decision statuses (mirrors DECISION_STATUSES). */
export const DECISION_STATUSES = ['proposed', 'accepted', 'implemented', 'superseded'] as const

export type DecisionStatus = (typeof DECISION_STATUSES)[number]

/** Insight subtypes (mirrors INSIGHT_TYPES). */
export const INSIGHT_TYPES = ['pattern', 'trend', 'gap', 'contradiction', 'recommendation'] as const

export type InsightType = (typeof INSIGHT_TYPES)[number]

export const INSIGHT_STATUSES = ['needs_review', 'accepted', 'rejected'] as const

/** Contradiction severities (mirrors CONTRADICTION_SEVERITIES). */
export const CONTRADICTION_SEVERITIES = ['high', 'medium', 'low'] as const

export type ContradictionSeverity = (typeof CONTRADICTION_SEVERITIES)[number]

/** Source types for provenance (mirrors SOURCE_TYPES). */
export const SOURCE_TYPES = ['git', 'markdown', 'chatgpt', 'commit', 'code', 'research'] as const

export type SourceType = (typeof SOURCE_TYPES)[number]

/** Report kinds (mirrors REPORT_TYPES). */
export const REPORT_TYPES = ['project-knowledge', 'research-gaps', 'implementation-plan', 'architecture', 'release-notes'] as const

export type ReportType = (typeof REPORT_TYPES)[number]

/** Entity kinds (mirrors ENTITY_KINDS). */
export const ENTITY_KINDS = ['module', 'engine', 'theory', 'metric', 'concept', 'person'] as const

export type EntityKind = (typeof ENTITY_KINDS)[number]
