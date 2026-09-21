/**
 * MKC API client — the ONLY file in the dashboard that touches the network.
 *
 * Contract source: backend/src/mkc (routers + models to_dict()).
 * - Base URL: VITE_MKC_API_URL at build time, overridable at runtime from the
 *   settings popover (localStorage).
 * - Auth: bearer token from localStorage. Never logged, never in URLs.
 * - Errors are normalized to ApiError: 401 invalid token, 404 not found,
 *   409 invalid transition (carries allowed_next_states), 5xx server error,
 *   status 0 = network unreachable.
 *
 * Mock mode: data calls automatically fall back to src/lib/mock.ts when the
 * API is unreachable, the token is missing/invalid, or the operator forces
 * it. The app state layer observes transitions via setMockListeners.
 */
import { mockApi } from './mock'
import type {
  ApiErrorInfo,
  Contradiction,
  Decision,
  Experiment,
  HealthStatus,
  Insight,
  KnowledgeDetail,
  KnowledgeObject,
  KnowledgeQuery,
  Paged,
  ReportMeta,
  ResearchItem,
  ResourceQuery,
  SearchResult,
  StatusSummary,
} from './types'

const TOKEN_KEY = 'mkc.api_token'
const BASE_KEY = 'mkc.api_base'
const DEFAULT_BASE = 'http://127.0.0.1:8000'

function normalizeBase(raw: string): string {
  const t = raw.trim()
  if (!t || t === '/') return ''
  return t.replace(/\/+$/, '')
}

export function getApiBase(): string {
  const stored = safeGet(BASE_KEY)
  if (stored !== null) return normalizeBase(stored)
  const env = import.meta.env.VITE_MKC_API_URL as string | undefined
  if (env !== undefined) return normalizeBase(env)
  return DEFAULT_BASE
}

export function setApiBase(raw: string): void {
  const v = normalizeBase(raw)
  if (v) safeSet(BASE_KEY, v)
  else safeRemove(BASE_KEY)
}

export function getToken(): string {
  return safeGet(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  const v = token.trim()
  if (v) safeSet(TOKEN_KEY, v)
  else safeRemove(TOKEN_KEY)
  // A new token resets the failure flags; the store re-probes.
  invalidToken = false
}

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage blocked (private mode): the app keeps working for the session.
  }
}

function safeRemove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly allowedNextStates?: string[]

  constructor(info: ApiErrorInfo) {
    super(info.detail)
    this.name = 'ApiError'
    this.status = info.status
    this.code = info.code
    this.detail = info.detail
    this.allowedNextStates = info.allowed_next_states
  }

  get isNetwork(): boolean {
    return this.status === 0
  }
}

function toApiError(status: number, data: unknown): ApiError {
  let code = 'error'
  let detail = `Request failed with HTTP ${status}.`
  let allowed: string[] | undefined
  if (data && typeof data === 'object' && 'detail' in data) {
    const d: unknown = (data as { detail: unknown }).detail
    if (typeof d === 'string') {
      code = status === 401 ? 'unauthorized' : status === 404 ? 'not_found' : 'error'
      detail = d
    } else if (Array.isArray(d)) {
      // FastAPI validation error: detail is a list of {loc, msg, type}.
      code = 'validation_error'
      const msgs = d
        .filter((x): x is { msg?: unknown } => Boolean(x && typeof x === 'object'))
        .map((x) => (typeof x.msg === 'string' ? x.msg : ''))
        .filter(Boolean)
      detail = msgs.length > 0 ? msgs.join('; ') : detail
    } else if (d && typeof d === 'object') {
      // MKC error envelope: {"detail": {"code", "detail", ...extra}}.
      const o = d as Record<string, unknown>
      code = typeof o.code === 'string' ? o.code : 'error'
      detail = typeof o.detail === 'string' ? o.detail : detail
      if (Array.isArray(o.allowed_next_states)) {
        allowed = o.allowed_next_states.filter((s): s is string => typeof s === 'string')
      }
    }
  }
  if (status === 401 && code === 'error') code = 'unauthorized'
  if (status === 404 && code === 'error') code = 'not_found'
  return new ApiError({ status, code, detail, allowed_next_states: allowed })
}

// ---------------------------------------------------------------------------
// Mock-mode flags (mutated here, observed by the app state layer)
// ---------------------------------------------------------------------------

let networkDown = false
let invalidToken = false
let mockForced = false

interface MockListeners {
  onNetwork?: (detail: string) => void
  onUnauthorized?: () => void
  onForced?: (forced: boolean) => void
}

let listeners: MockListeners = {}

export function setMockListeners(l: MockListeners): void {
  listeners = l
}

export function setMockForced(forced: boolean): void {
  if (mockForced !== forced) {
    mockForced = forced
    listeners.onForced?.(forced)
  }
}

export function isMockForced(): boolean {
  return mockForced
}

/**
 * Clear the derived failure flags so the next request re-probes the live
 * API. Used by the state layer after the operator edits the base URL or
 * token (setToken already resets invalidToken on its own).
 */
export function resetApiState(): void {
  networkDown = false
  invalidToken = false
}

function mockActive(): boolean {
  return mockForced || networkDown || invalidToken || !getToken()
}

/** Read-only probe of the current mock flags, so the UI can compute the
 *  banner copy ("no API token" vs "API unreachable" vs "forced") without
 *  awaiting a request. */
export function isMockActiveNow(): {
  active: boolean
  forced: boolean
  networkDown: boolean
  invalidToken: boolean
  missingToken: boolean
} {
  return {
    active: mockActive(),
    forced: mockForced,
    networkDown,
    invalidToken,
    missingToken: !getToken(),
  }
}

function markNetworkDown(detail: string): void {
  networkDown = true
  listeners.onNetwork?.(detail)
}

function markInvalidToken(): void {
  invalidToken = true
  listeners.onUnauthorized?.()
}

// ---------------------------------------------------------------------------
// Core request
// ---------------------------------------------------------------------------

function buildUrl(path: string): string {
  return getApiBase() + path
}

function authHeaders(init?: RequestInit): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (init?.body !== undefined) headers['Content-Type'] = 'application/json'
  return headers
}

async function liveJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path), { ...init, headers: authHeaders(init) })
  } catch {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      detail: 'Cannot reach the MKC API. Is the service running? Check the base URL in Settings.',
    })
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (!res.ok) throw toApiError(res.status, data)
  return data as T
}

async function liveText(path: string): Promise<string> {
  let res: Response
  try {
    res = await fetch(buildUrl(path), { headers: authHeaders() })
  } catch {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      detail: 'Cannot reach the MKC API. Is the service running? Check the base URL in Settings.',
    })
  }
  if (!res.ok) throw toApiError(res.status, null)
  return res.text()
}

/** Live-or-mock dispatch for a data endpoint. */
async function dataRequest<T>(path: string, mock: () => T, init?: RequestInit): Promise<T> {
  if (mockActive()) return mock()
  try {
    return await liveJson<T>(path, init)
  } catch (e) {
    if (e instanceof ApiError && e.isNetwork) {
      markNetworkDown(e.detail)
      return mock()
    }
    if (e instanceof ApiError && e.status === 401) {
      markInvalidToken()
      return mock()
    }
    throw e
  }
}

function qs(params: Record<string, string | number | undefined>): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  }
  return parts.length > 0 ? `?${parts.join('&')}` : ''
}

// ---------------------------------------------------------------------------
// Public surface (mock-aware)
// ---------------------------------------------------------------------------

/** Raw health probe, always live (public endpoint). Throws ApiError on
 *  network failure — the status dot uses this to show green/red. */
export async function fetchHealth(): Promise<HealthStatus> {
  return liveJson<HealthStatus>('/healthz')
}

/** Mock-aware health (pages use this). */
export function healthz(): Promise<HealthStatus> {
  if (mockActive()) return Promise.resolve(mockApi.healthz())
  return fetchHealth().catch((e) => {
    if (e instanceof ApiError && e.isNetwork) {
      markNetworkDown(e.detail)
      return mockApi.healthz()
    }
    throw e
  })
}

export function metricsText(): Promise<string> {
  if (mockActive()) return Promise.resolve(mockApi.metrics())
  return liveText('/metrics').catch((e) => {
    if (e instanceof ApiError && e.isNetwork) {
      markNetworkDown(e.detail)
      return mockApi.metrics()
    }
    throw e
  })
}

export function status(): Promise<StatusSummary> {
  return dataRequest<StatusSummary>('/api/v1/status', () => mockApi.status())
}

export function listKnowledge(query: KnowledgeQuery = {}): Promise<Paged<KnowledgeObject>> {
  const q = qs({
    type: query.type,
    lifecycle_state: query.lifecycle_state,
    q: query.q,
    page: query.page,
    page_size: query.page_size,
  })
  return dataRequest<Paged<KnowledgeObject>>(`/api/v1/knowledge${q}`, () => mockApi.listKnowledge(query))
}

export function getKnowledge(id: string): Promise<KnowledgeDetail> {
  return dataRequest<KnowledgeDetail>(`/api/v1/knowledge/${encodeURIComponent(id)}`, () => mockApi.getKnowledge(id))
}

export function listResearch(query: ResourceQuery = {}): Promise<Paged<ResearchItem>> {
  const q = qs({ status: query.status, knowledge_id: query.knowledge_id, page: query.page, page_size: query.page_size })
  return dataRequest<Paged<ResearchItem>>(`/api/v1/research${q}`, () => mockApi.listResearch(query))
}

export function getResearch(id: string): Promise<ResearchItem> {
  return dataRequest<ResearchItem>(`/api/v1/research/${encodeURIComponent(id)}`, () => mockApi.getResearch(id))
}

export function listDecisions(query: ResourceQuery = {}): Promise<Paged<Decision>> {
  const q = qs({ status: query.status, knowledge_id: query.knowledge_id, page: query.page, page_size: query.page_size })
  return dataRequest<Paged<Decision>>(`/api/v1/decisions${q}`, () => mockApi.listDecisions(query))
}

export function getDecision(id: string): Promise<Decision> {
  return dataRequest<Decision>(`/api/v1/decisions/${encodeURIComponent(id)}`, () => mockApi.getDecision(id))
}

export function listExperiments(query: ResourceQuery = {}): Promise<Paged<Experiment>> {
  const q = qs({ status: query.status, knowledge_id: query.knowledge_id, page: query.page, page_size: query.page_size })
  return dataRequest<Paged<Experiment>>(`/api/v1/experiments${q}`, () => mockApi.listExperiments(query))
}

export function getExperiment(id: string): Promise<Experiment> {
  return dataRequest<Experiment>(`/api/v1/experiments/${encodeURIComponent(id)}`, () => mockApi.getExperiment(id))
}

// Intelligence surfaces — the backend may not serve these routes yet (404 is
// expected until they land). Callers catch ApiError 404 and render the
// "endpoint not available yet" state instead of crashing.
export function listInsights(): Promise<Insight[]> {
  return dataRequest<Insight[]>('/api/v1/insights', () => mockApi.listInsights())
}

export function listContradictions(): Promise<Contradiction[]> {
  return dataRequest<Contradiction[]>('/api/v1/contradictions', () => mockApi.listContradictions())
}

export function listReports(): Promise<ReportMeta[]> {
  return dataRequest<ReportMeta[]>('/api/v1/reports', () => mockApi.listReports())
}

/** Full-text search over knowledge (GET /api/v1/knowledge?q=), timed. */
export async function searchKnowledge(query: KnowledgeQuery): Promise<SearchResult> {
  if (mockActive()) return mockApi.searchKnowledge(query)
  const started = performance.now()
  try {
    const q = qs({
      q: query.q,
      type: query.type,
      lifecycle_state: query.lifecycle_state,
      page: 1,
      page_size: 50,
    })
    const paged = await liveJson<Paged<KnowledgeObject>>(`/api/v1/knowledge${q}`)
    return {
      query: query.q ?? '',
      total: paged.total,
      elapsed_ms: Math.round(performance.now() - started),
      items: paged.items.map((item, i) => ({ ...item, score: 0, rank: i + 1 })),
    }
  } catch (e) {
    if (e instanceof ApiError && e.isNetwork) {
      markNetworkDown(e.detail)
      return mockApi.searchKnowledge(query)
    }
    if (e instanceof ApiError && e.status === 401) {
      markInvalidToken()
      return mockApi.searchKnowledge(query)
    }
    throw e
  }
}
