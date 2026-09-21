import { useState } from 'react'
import { listResearch } from '../lib/api'
import { RESEARCH_STATUSES } from '../lib/constants'
import { useMkc, useQuery } from '../state'
import { Badge, Button, Card, PageHeader, Select, Spinner, StateMessage, badgeToneForState } from '../components/ui'

export function ResearchPage() {
  const { key } = useMkc()
  const [status, setStatus] = useState('')

  const query = useQuery(
    () => listResearch({ status: status || undefined, page: 1, page_size: 50 }),
    [key, status],
    key,
  )
  const items = query.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="Research"
        subtitle={query.data ? <span>{query.data.total} research topics</span> : undefined}
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

      {query.loading && <Spinner label="Loading research…" />}
      {!query.loading && query.error && (
        <StateMessage title="Could not load research" detail={query.error} tone="danger" action={<Button onClick={query.reload}>Retry</Button>} />
      )}
      {!query.loading && !query.error && items.length === 0 && (
        <StateMessage
          title={status ? `No research with status “${status}”` : 'No research topics yet'}
          detail={status ? 'Try another status filter.' : 'Topics appear once a question enters the research pipeline.'}
        />
      )}
      {!query.loading && !query.error && items.length > 0 && (
        <div className="grid gap-3 xl:grid-cols-2">
          {items.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-semibold">{r.title}</h3>
                  <p className="mt-0.5 font-mono text-xs text-faint">
                    {r.id} · {r.topic}
                  </p>
                </div>
                <Badge tone={badgeToneForState(r.status)}>{r.status}</Badge>
              </div>
              <p className="mt-2.5 text-sm text-muted">
                <span className="text-faint">Hypothesis: </span>
                {r.hypothesis}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                <span>
                  <span className="text-faint">evidence </span>
                  <span className="font-mono">{r.evidence_count}</span>
                </span>
                <span>
                  <span className="text-faint">validation </span>
                  <Badge tone={r.validation_level === 'reproduced' ? 'ok' : r.validation_level === 'single-source' ? 'info' : 'neutral'}>{r.validation_level}</Badge>
                </span>
                {r.related_modules.length > 0 && (
                  <span className="flex items-center gap-1">
                    <span className="text-faint">modules</span>
                    {r.related_modules.map((m) => (
                      <span key={m} className="rounded bg-raised px-1.5 py-0.5 font-mono text-[11px]">
                        {m}
                      </span>
                    ))}
                  </span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
