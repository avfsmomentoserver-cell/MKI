import { useEffect, useRef, useState } from 'react'
import { getApiBase, getToken, setApiBase, setToken } from '../lib/api'
import { useMkc } from '../state'
import { Button, Input } from './ui'

/** Popover holding the API connection settings: base URL, bearer token and
 *  the mock-mode override. Saves go straight to localStorage via lib/api
 *  and bump the global state key so every page re-fetches against the new
 *  endpoint immediately.
 *
 * Note on the token: it is persisted in localStorage on this machine
 * (localhost, single-operator dashboard) so a page reload does not require
 * re-pasting it. It is only ever sent as an Authorization header to the
 * configured base URL. */
export function SettingsPopover() {
  const [open, setOpen] = useState(false)
  const [base, setBase] = useState(getApiBase())
  const [token, setTok] = useState(getToken())
  const [testResult, setTestResult] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [saved, setSaved] = useState(false)
  const { mockForced, setMockForced, reprobe, apiBase } = useMkc()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const save = () => {
    setApiBase(base)
    setToken(token)
    reprobe()
    setSaved(true)
    window.setTimeout(() => setSaved(false), 1500)
    setTestResult(null)
  }

  const test = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await fetch(base ? `${base.replace(/\/+$/, '')}/healthz` : '/healthz', { headers: { Accept: 'application/json' } })
      const ok = r.ok
      setTestResult(ok ? 'OK — API reachable' : `HTTP ${r.status}`)
    } catch {
      setTestResult('Unreachable — check the base URL')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="rounded-md border border-line bg-raised p-1.5 text-muted hover:text-ink"
        aria-label="Settings"
        aria-expanded={open}
      >
        <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true">
          <circle cx="10" cy="10" r="2.6" />
          <path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M15.3 4.7l-1.6 1.6M6.3 13.7l-1.6 1.6" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="API settings"
          className="absolute right-0 z-50 mt-2 w-80 rounded-lg border border-line bg-panel p-4 shadow-2xl"
        >
          <h3 className="text-sm font-semibold">API settings</h3>
          <p className="mt-1 text-xs text-faint">
            Currently targeting <span className="font-mono break-all">{apiBase || '(same origin — dev proxy)'}</span>
          </p>

          <label className="mt-3 block text-xs font-medium text-muted" htmlFor="api-base">
            Base URL
          </label>
          <Input
            id="api-base"
            className="mt-1 w-full font-mono text-xs"
            value={base}
            onChange={(e) => setBase(e.target.value)}
            placeholder="(empty = same origin / default 127.0.0.1:8000)"
          />

          <label className="mt-3 block text-xs font-medium text-muted" htmlFor="api-token">
            Bearer token
          </label>
          <Input
            id="api-token"
            className="mt-1 w-full font-mono text-xs"
            value={token}
            onChange={(e) => setTok(e.target.value)}
            placeholder="mkc-…  (empty = no token)"
            type="password"
            autoComplete="off"
          />
          <p className="mt-1.5 text-[11px] leading-snug text-faint">
            Stored in <span className="font-mono">localStorage</span> on this machine so reloads keep working; sent only
            as an Authorization header to the base URL above. Leave empty for a tokenless local instance.
          </p>

          <label className="mt-3 flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={mockForced}
              onChange={(e) => setMockForced(e.target.checked)}
              className="size-3.5 accent-[var(--color-accent)]"
            />
            Force mock mode (show sample data even if the API is up)
          </label>

          <div className="mt-4 flex items-center gap-2">
            <Button variant="primary" onClick={save} className="flex-1">
              {saved ? 'Saved' : 'Save'}
            </Button>
            <Button onClick={test} disabled={testing}>
              {testing ? 'Testing…' : 'Test connection'}
            </Button>
          </div>
          {testResult && (
            <p className={`mt-2 text-xs ${testResult.startsWith('OK') ? 'text-ok' : 'text-danger'}`} role="status">
              {testResult}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
