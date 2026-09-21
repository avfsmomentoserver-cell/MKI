import { useState } from 'react'
import { listExperiments } from '../lib/api'
import { RESEARCH_STATUSES } from '../lib/constants'
import type { Experiment } from '../lib/types'
import { useMkc, useQuery } from '../state'
import { Drawer } from '../components/Drawer'
import { Badge, Button, Card, PageHeader, Select, Spinner, StateMessage, badgeToneForState } from '../components/ui'

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md border border-line bg-raised/50 px-2.5 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-faint">{k}</p>
      <p className="font-mono text-xs text-ink">{v}</p>
    </div>
  )
}

function ExperimentDetail({ exp }: { exp: Experiment }) {
  const stats = Object.entries(exp.statistics_json ?? {})
  return (
    <div className="space-y-5">
      {exp.status === 'failed' && (
        <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          <strong>FAILED experiment.</strong> First-class result: the hypothesis was rejected. The full record below is kept so
          the reasoning is auditable.
        </div>
      )}
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Hypothesis tested</h3>
        <p className="text-sm text-muted">{exp.hypothesis_tested}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Dataset / method</h3>
        <p className="text-sm text-muted">{exp.dataset}</p>
        <p className="mt-1 text-sm text-muted">{exp.method}</p>
      </section>
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Result</h3>
        <p className="whitespace-pre-wrap text-sm">{exp.result}</p>
      </section>
      {stats.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Statistics</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {stats.map(([k, v]) => (
              <Stat key={k} k={k.replace(/_/g, ' ')} v={typeof v === 'object' ? JSON.stringify(v) : String(v)} />
            ))}
          </div>
        </section>
      )}
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Conclusion</h3>
        <p className="text-sm">{exp.conclusion}</p>
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Reproducibility</h3>
          <p className="text-xs text-muted">{exp.reproducibility}</p>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">Limitations</h3>
          <p className="text-xs text-muted">{exp.limitations}</p>
        </section>
      </div>
    </div>
  )
}

export function ExperimentsPage() {
  const { key } = useMkc()
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<Experiment | null>(null)

  const query = useQuery(
    () => listExperiments({ status: status || undefined, page: 1, page_size: 50 }),
    [key, status],
    key,
  )
  const items = query.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="Experiments"
        subtitle={
          query.data ? (
            <span>
              {query.data.total} experiments · failed results are shown in full, not hidden
            </span>
          ) : undefined
        }
        actions={
          <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {RESEARCH_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        }
      />

      {query.loading && <Spinner label="Loading experiments…" />}
      {!query.loading && query.error && (
        <StateMessage title="Could not load experiments" detail={query.error} tone="danger" action={<Button onClick={query.reload}>Retry</Button>} />
      )}
      {!query.loading && !query.error && items.length === 0 && (
        <StateMessage
          title={status ? `No experiments with status “${status}”` : 'No experiments yet'}
          detail={status ? 'Try another status filter.' : 'Experiments land here when a hypothesis enters the test stage.'}
        />
      )}
      {!query.loading && !query.error && items.length > 0 && (
        <Card>
          <ul className="divide-y divide-line">
            {items.map((exp) => (
              <li key={exp.id}>
                <button
                  type="button"
                  onClick={() => setSelected(exp)}
                  className="block w-full px-4 py-3 text-left transition-colors hover:bg-raised/60 focus-visible:bg-raised/60"
                >
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{exp.title}</span>
                    <Badge tone={badgeToneForState(exp.status)}>{exp.status}</Badge>
                    <span className="font-mono text-xs text-faint">{exp.id}</span>
                  </div>
                  <p className="mt-1 truncate text-xs text-muted">{exp.hypothesis_tested}</p>
                  <p className="mt-0.5 truncate text-xs text-faint">{exp.conclusion}</p>
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
            </span>
          }
          onClose={() => setSelected(null)}
        >
          <ExperimentDetail exp={selected} />
        </Drawer>
      )}
    </div>
  )
}
