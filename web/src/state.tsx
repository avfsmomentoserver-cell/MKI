/**
 * App state layer.
 *
 * - `useQuery`: generic data hook with loading/error states and race-safe
 *   updates (aborted queries never overwrite fresh results).
 * - `MkcProvider`: subscribes to the mock-mode listeners in lib/api.ts and
 *   exposes { mockActive, mockReason, mockForced, setMockForced, apiBase,
 *   key, reprobe }. `key` bumps whenever the API base/token changes or the
 *   operator requests a re-probe, so every page re-fetches (mock -> live or
 *   live -> mock transitions are reflected immediately).
 *
 * No Redux: a single context plus one hook is all this dashboard needs.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DependencyList,
  type ReactNode,
} from 'react'
import {
  getApiBase,
  isMockActiveNow,
  resetApiState,
  setMockForced as apiSetMockForced,
  setMockListeners,
} from './lib/api'
import { isApiError, type ApiError } from './lib/errors'

export interface QueryState<T> {
  loading: boolean
  error: string | null
  apiError: ApiError | null
  data: T | null
  reload: () => void
}

/** Fetch via `fetcher` (usually a lib/api.ts function), with loading/error
 *  state. `deps` drives re-fetching; in-flight fetches are invalidated when
 *  deps change or the component unmounts, so a slow stale response can never
 *  clobber a newer one. */
export function useQuery<T>(fetcher: () => Promise<T>, deps: DependencyList, reloadSignal: number): QueryState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<ApiError | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let stale = false
    setLoading(true)
    setError(null)
    setApiError(null)
    fetcher()
      .then((d) => {
        if (!stale) setData(d)
      })
      .catch((e: unknown) => {
        if (stale) return
        if (isApiError(e)) {
          setApiError(e)
          setError(
            e.status === 404
              ? `Endpoint not available yet (404): ${e.detail}`
              : e.isNetwork
                ? `Cannot reach the API: ${e.detail}`
                : e.detail,
          )
        } else {
          setError(e instanceof Error ? e.message : 'Unexpected error')
        }
      })
      .finally(() => {
        if (!stale) setLoading(false)
      })
    return () => {
      stale = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetcher/deps are
    // supplied per call site; dep identity is the contract.
  }, [...deps, reloadSignal, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { loading, error, apiError, data, reload }
}

export type MockReason = 'forced' | 'unreachable' | 'unauthorized' | 'missing-token'

interface MockFlags {
  forced: boolean
  networkDown: boolean
  invalidToken: boolean
  missingToken: boolean
}

function deriveReason(f: MockFlags): MockReason | null {
  if (!f.forced && !f.networkDown && !f.invalidToken && !f.missingToken) return null
  if (f.forced) return 'forced'
  if (f.networkDown) return 'unreachable'
  if (f.invalidToken) return 'unauthorized'
  return 'missing-token'
}

export interface MkcState {
  /** True whenever the data being shown comes from the mock layer. */
  mockActive: boolean
  /** Why mock mode is on (null when live). Drives the banner copy. */
  mockReason: MockReason | null
  mockForced: boolean
  setMockForced: (v: boolean) => void
  /** API base the client is currently targeting. */
  apiBase: string
  /** Bumped when settings change or a re-probe is requested; pages refetch. */
  key: number
  /** Ask the client to try the live API again (clears the unreachable flag). */
  reprobe: () => void
}

const MkcContext = createContext<MkcState | null>(null)

export function MkcProvider({ children }: { children: ReactNode }) {
  const [flags, setFlags] = useState<MockFlags>(() => {
    const s = isMockActiveNow()
    return { forced: s.forced, networkDown: s.networkDown, invalidToken: s.invalidToken, missingToken: s.missingToken }
  })
  const [key, setKey] = useState(0)
  const keyRef = useRef(0)
  const bump = useCallback(() => {
    keyRef.current += 1
    setKey(keyRef.current)
  }, [])

  useEffect(() => {
    setMockListeners({
      onNetwork: () => setFlags((f) => ({ ...f, networkDown: true })),
      onUnauthorized: () => setFlags((f) => ({ ...f, invalidToken: true })),
      onForced: (forced) => setFlags((f) => ({ ...f, forced })),
    })
    return () => setMockListeners({})
  }, [])

  const reprobe = useCallback(() => {
    resetApiState()
    bump()
  }, [bump])

  const setForced = useCallback(
    (v: boolean) => {
      apiSetMockForced(v)
      setFlags((f) => ({ ...f, forced: v }))
      // A forced/mock state change must not silently keep stale live data.
      bump()
    },
    [bump],
  )

  const value = useMemo<MkcState>(
    () => ({
      mockActive: deriveReason(flags) !== null,
      mockReason: deriveReason(flags),
      mockForced: flags.forced,
      setMockForced: setForced,
      apiBase: getApiBase(),
      key,
      reprobe,
    }),
    [flags, key, setForced, reprobe],
  )

  return <MkcContext.Provider value={value}>{children}</MkcContext.Provider>
}

export function useMkc(): MkcState {
  const ctx = useContext(MkcContext)
  if (!ctx) throw new Error('useMkc must be used inside <MkcProvider>')
  return ctx
}
