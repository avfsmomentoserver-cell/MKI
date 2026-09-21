import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { fetchHealth } from '../lib/api'
import { useNow } from '../lib/format'
import { useMkc, type MockReason } from '../state'
import { useTheme } from '../theme'
import { SettingsPopover } from './SettingsPopover'

const NAV: { to: string; label: string }[] = [
  { to: '/', label: 'Overview' },
  { to: '/knowledge', label: 'Knowledge' },
  { to: '/research', label: 'Research' },
  { to: '/experiments', label: 'Experiments' },
  { to: '/decisions', label: 'Decisions' },
  { to: '/insights', label: 'Insights' },
  { to: '/documentation', label: 'Documentation' },
  { to: '/research-dashboard', label: 'Research Dashboard' },
  { to: '/books', label: 'Books' },
  { to: '/reports', label: 'Reports' },
  { to: '/search', label: 'Search' },
  { to: '/system', label: 'System' },
]

function pageTitle(pathname: string): string {
  const found = NAV.find((n) => n.to === pathname)
  return found ? found.label : 'System'
}

const MOCK_COPY: Record<MockReason, string> = {
  forced: 'You are looking at sample data — mock mode was forced in Settings.',
  unreachable: 'MKC API unreachable — showing sample data. Fix the connection or check Settings.',
  unauthorized: 'API token rejected (401) — showing sample data. Check the token in Settings.',
  'missing-token': 'No API token configured — showing sample data. Add one in Settings.',
}

function HealthDot() {
  const [state, setState] = useState<{ live: boolean; ok: boolean; detail: string; checkedAt: number }>({
    live: false,
    ok: false,
    detail: 'checking…',
    checkedAt: 0,
  })
  useNow(30_000)

  useEffect(() => {
    let stale = false
    fetchHealth()
      .then((h) => {
        if (!stale)
          setState({ live: true, ok: h.status === 'ok', detail: `API ${h.status} · db ${h.database}`, checkedAt: Date.now() })
      })
      .catch(() => {
        if (!stale) setState((s) => ({ ...s, live: false, ok: false, detail: 'API unreachable', checkedAt: Date.now() }))
      })
    return () => {
      stale = true
    }
  })

  const color = state.live ? (state.ok ? 'bg-ok' : 'bg-warn') : 'bg-danger'
  return (
    <span
      className="inline-flex items-center gap-2 rounded-md border border-line bg-raised px-2.5 py-1 text-xs text-muted"
      title={`${state.detail} · ${new Date(state.checkedAt).toLocaleTimeString()}`}
      role="status"
      aria-label={`API health: ${state.detail}`}
    >
      <span className={`size-2 rounded-full ${color}`} aria-hidden="true" />
      API {state.live ? (state.ok ? 'healthy' : state.detail) : 'offline'}
    </span>
  )
}

function MockBanner() {
  const { mockActive, mockReason } = useMkc()
  if (!mockActive || !mockReason) return null
  return (
    <div
      className="border-b border-warn/40 bg-warn/15 px-4 py-1.5 text-center text-xs font-medium text-warn"
      role="alert"
      aria-live="assertive"
    >
      <span className="mr-2 inline-block size-2 rounded-full bg-warn" aria-hidden="true" />
      MOCK MODE — {MOCK_COPY[mockReason]}
    </div>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const [theme, toggleTheme] = useTheme()
  const { pathname } = useLocation()

  return (
    <div className="flex h-full min-h-screen flex-col">
      <MockBanner />
      <div className="flex flex-1">
        <aside className="flex w-52 shrink-0 flex-col border-r border-line bg-panel" aria-label="Primary">
          <div className="border-b border-line px-4 py-3.5">
            <p className="text-sm font-semibold tracking-tight">MKC</p>
            <p className="text-[11px] text-faint">Momento Knowledge Core</p>
          </div>
          <nav className="flex-1 overflow-y-auto px-2 py-2" aria-label="Main navigation">
            <ul className="space-y-0.5">
              {NAV.map((n) => (
                <li key={n.to}>
                  <NavLink
                    to={n.to}
                    end={n.to === '/'}
                    className={({ isActive }) =>
                      `block rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                        isActive ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:bg-raised hover:text-ink'
                      }`
                    }
                  >
                    {n.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line bg-panel px-4">
            <h2 className="truncate text-sm font-medium text-muted">{pageTitle(pathname)}</h2>
            <div className="flex items-center gap-2">
              <HealthDot />
              <button
                type="button"
                onClick={toggleTheme}
                className="rounded-md border border-line bg-raised p-1.5 text-muted hover:text-ink"
                aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                {theme === 'dark' ? (
                  <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
                    <circle cx="10" cy="10" r="3.6" />
                    <path d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6L16 16M16 4l-1.4 1.4M5.4 14.6L4 16" strokeLinecap="round" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
                    <path d="M16.5 11.5A7 7 0 0 1 8.5 3.5a7 7 0 1 0 8 8Z" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
              <SettingsPopover />
            </div>
          </header>
          <main className="min-w-0 flex-1 overflow-y-auto p-5">{children}</main>
        </div>
      </div>
    </div>
  )
}
