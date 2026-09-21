/**
 * Small display helpers shared by pages. All data they render comes from the
 * API contract (types.ts); nothing here invents domain facts.
 */
import { useEffect, useState } from 'react'

/** "0.94" -> "94%". Values are expected to be 0..1; clamped so a backend
 *  drift (e.g. 0-100 scale) degrades to a visible 100% instead of "9400%". */
export function pct(v: number): string {
  if (!Number.isFinite(v)) return '—'
  const n = Math.min(100, Math.max(0, Math.round(v * 100)))
  return `${n}%`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "17:42:05" or a relative "3 h ago" for entries within ~3 days. */
export function fmtAuditTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const delta = Date.now() - d.getTime()
  if (delta > 0 && delta < 3 * 24 * 3600_000) {
    const mins = Math.floor(delta / 60_000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins} min ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs} h ago`
    return `${Math.floor(hrs / 24)} d ago`
  }
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return ''
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

/** "0a1b2c3d…" style short hash for provenance displays. */
export function shortHash(h: string | null | undefined, n = 8): string {
  if (!h) return ''
  return h.length > n ? `${h.slice(0, n)}…` : h
}

/** Re-evaluates `compute()` now and every `ms` — used by the health dot. */
export function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(id)
  }, [ms])
  return now
}
