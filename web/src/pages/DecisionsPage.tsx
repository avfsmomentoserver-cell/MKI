import { useState } from 'react'
import { listDecisions } from '../lib/api'
import { DECISION_STATUSES } from '../lib/constants'
import type { Decision } from '../lib/types'
import { fmtDate } from '../lib/format'
import { useMkc, useQuery } from '../state'
import { Drawer } from '../components/Drawer'
import { Badge, Button, Card, PageHeader, Select, Spinner, StateMessage, badgeToneForState } from '../components/ui'

function DecisionDetail({ d }: { d: Decision }) {
  return (
    <div className="space-y-5">
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Context</h3>
        <p className="text-sm text-muted">{d.context}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Problem</h3>
        <p className="text-sm text-muted">{d.problem}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Alternatives considered</h3>
        <p className="text-sm text-muted">{d.alternatives}</p>
      </section>
      <section className="rounded-md border border-accent/30 bg-accent-soft/60 px-3 py-2.5">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-accent">Decision</h3>
        <p className="text-sm">{d.decision_text}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Rationale</h3>
        <p className="text-sm">{d.reason}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Evidence</h3>
        <p className="font-mono text-xs text-muted">{d.evidence}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Affected components</h3>
        <div className="flex flex-wrap gap-1.5">
          {d.affected_components.length > 0 ? (
            d.affected_components.map((c) => (
              <span key={c} className="rounded bg-raised px-1.5 py-0.5 font-mono text-[11px] text-muted">
                {c}
              </span>
            ))
          ) : (
            <span className="text-xs text-faint">none recorded</span>
          )}
        </div>
      </section>
      {d.superseded_by && (
        <p className="rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
          Superseded by <span className="font-mono">{d.superseded_by}</span> — see the audit trail for the replacement decision.
        </p>
      )}
    </div>
  )
}

export function DecisionsPage() {
  const { key } = useMkc()
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<Decision | null>(null)

  const query = useQuery(
    () => listDecisions({ status: status || undefined, page: 1, page_size: 50 }),
    [key, status],
    key,
  )
  const items = query.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="Decisions"
        subtitle={query.data ? <span>{query.data.total} recorded decisions with full rationale chains</span> : undefined}
        actions={
          <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {DECISION_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        }
      />

      {query.loading && <Spinner label="Loading decisions…" />}
      {!query.loading && query.error && (
        <StateMessage title="Could not load decisions" detail={query.error} tone="danger" action={<Button onClick={query.reload}>Retry</Button>} />
      )}
      {!query.loading && !query.error && items.length === 0 && (
        <StateMessage
          title={status ? `No decisions with status “${status}”` : 'No recorded decisions'}
          detail={status ? 'Try another status filter.' : 'Decisions are captured with context, alternatives and evidence.'}
        />
      )}
      {!query.loading && !query.error && items.length > 0 && (
        <Card>
          <ul className="divide-y divide-line">
            {items.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => setSelected(d)}
                  className="block w-full px-4 py-3 text-left transition-colors hover:bg-raised/60 focus-visible:bg-raised/60"
                >
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{d.title}</span>
                    <Badge tone={badgeToneForState(d.status)}>{d.status}</Badge>
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-faint">
                    <span className="font-mono">{d.id}</span>
                    <span>{d.author}</span>
                    <span>{fmtDate(d.decided_at)}</span>
                    {d.superseded_by && <Badge tone="warn">superseded</Badge>}
                  </div>
                  <p className="mt-1 truncate text-xs text-muted">{d.decision_text}</p>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {selected && (
        <Drawer
          title={selected.title}
          subtitle={
            <span className="flex items-center gap-2">
              <span className="font-mono">{selected.id}</span>
              <Badge tone={badgeToneForState(selected.status)}>{selected.status}</Badge>
              <span>{selected.author} · {fmtDate(selected.decided_at)}</span>
            </span>
          }
          onClose={() => setSelected(null)}
        >
          <DecisionDetail d={selected} />
        </Drawer>
      )}
    </div>
  )
}
