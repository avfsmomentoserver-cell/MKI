/** Normalized API error shared by the client and the mock layer. */

export interface ApiErrorInfo {
  status: number
  code: string
  detail: string
  allowed_next_states?: string[]
}

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

/** Narrow unknown throwables to ApiError. api.ts is the only module that
 *  performs fetches, so this is the full set of normalized errors. */
export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError
}
