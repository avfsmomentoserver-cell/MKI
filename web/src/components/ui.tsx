import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

export type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info' | 'accent'

const BADGE_TONES: Record<Tone, string> = {
  neutral: 'bg-raised text-muted border-line',
  ok: 'bg-ok/15 text-ok border-ok/40',
  warn: 'bg-warn/15 text-warn border-warn/40',
  danger: 'bg-danger/15 text-danger border-danger/40',
  info: 'bg-info/15 text-info border-info/40',
  accent: 'bg-accent-soft text-accent border-accent/30',
}

export function badgeToneForState(state: string): Tone {
  switch (state) {
    case 'production':
    case 'validated':
    case 'implemented':
    case 'accepted':
    case 'succeeded':
    case 'resolved':
      return 'ok'
    case 'researching':
    case 'running':
    case 'validating':
    case 'observed':
    case 'hypothesis':
    case 'question':
    case 'needs_review':
    case 'proposed':
    case 'paused':
      return 'info'
    case 'deprecated':
    case 'superseded':
    case 'archived':
      return 'neutral'
    case 'contradicted':
    case 'rejected':
    case 'failed':
    case 'flagged':
      return 'danger'
    default:
      return 'accent'
  }
}

/** Tone for a lifecycle state; unknown states (future backend values) get
 *  the accent tone rather than a wrong semantic colour. */
export function lifecycleTone(state: string): Tone {
  switch (state) {
    case 'idea':
      return 'neutral'
    case 'experiment':
      return 'info'
    case 'unknown':
      return 'warn'
    default:
      return badgeToneForState(state)
  }
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-panel ${className}`}>{children}</div>
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] leading-none ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted" role="status" aria-live="polite">
      <span className="size-4 animate-spin rounded-full border-2 border-line border-t-accent" aria-hidden="true" />
      {label}
    </div>
  )
}

export function StateMessage({
  title,
  detail,
  action,
  tone = 'neutral',
}: {
  title: string
  detail?: string
  action?: ReactNode
  tone?: Tone
}) {
  const color =
    tone === 'danger' ? 'text-danger' : tone === 'warn' ? 'text-warn' : tone === 'info' ? 'text-info' : 'text-muted'
  return (
    <div className={`rounded-lg border border-dashed border-line bg-panel/40 p-8 text-center ${color}`}>
      <p className="text-sm font-medium">{title}</p>
      {detail && <p className="mx-auto mt-1 max-w-md text-xs text-faint">{detail}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'outline'
}

export function Button({ variant = 'outline', className = '', ...rest }: ButtonProps) {
  const base =
    'inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50'
  const styles =
    variant === 'primary'
      ? 'border-accent/40 bg-accent text-white hover:bg-accent/90 dark:text-[#0d1117]'
      : 'border-line bg-raised text-ink hover:border-faint/60'
  return <button type="button" className={`${base} ${styles} ${className}`} {...rest} />
}

export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`h-8 rounded-md border border-line bg-panel px-2.5 text-sm text-ink placeholder:text-faint focus:border-accent/50 ${className}`}
      {...rest}
    />
  )
}

export function Select({ className = '', ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`h-8 rounded-md border border-line bg-panel px-2 text-sm text-ink focus:border-accent/50 ${className}`}
      {...rest}
    />
  )
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number
  pageSize: number
  total: number
  onChange: (p: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (pages <= 1) return null
  return (
    <nav className="flex items-center justify-end gap-3 border-t border-line px-4 py-2 text-xs text-muted" aria-label="Pagination">
      <button
        type="button"
        className="rounded border border-line px-2 py-1 hover:border-faint/60 disabled:opacity-40"
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        ← Prev
      </button>
      <span aria-live="polite">
        page {page} / {pages} · {total} items
      </span>
      <button
        type="button"
        className="rounded border border-line px-2 py-1 hover:border-faint/60 disabled:opacity-40"
        onClick={() => onChange(page + 1)}
        disabled={page >= pages}
        aria-label="Next page"
      >
        Next →
      </button>
    </nav>
  )
}

/** One-liner for provenance, used where a full table is too heavy. */
export function ProvenanceInline({ p }: { p: { source_type?: string; file_path?: string; commit_hash?: string; date?: string | null } }) {
  const bits: string[] = []
  if (p.source_type) bits.push(p.source_type)
  if (p.file_path) bits.push(p.file_path)
  if (p.commit_hash) bits.push(p.commit_hash.slice(0, 8))
  if (p.date) bits.push(p.date)
  if (bits.length === 0) return <span className="text-faint">no provenance</span>
  return <span className="font-mono text-[11px] text-faint">{bits.join(' · ')}</span>
}
