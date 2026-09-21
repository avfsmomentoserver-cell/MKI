import { useNavigate } from 'react-router-dom'
import { listContradictions, status } from '../lib/api'
import { LIFECYCLE_STATES } from '../lib/constants'
import { fmtAuditTime, fmtDate, pct } from '../lib/format'
import { useMkc, useQuery } from '../state'
import { BarChart, Sparkline } from '../components/charts'
import { Badge, Card, PageHeader, Spinner, StateMessage, badgeToneForState, lifecycleTone } from '../components/ui'

export function OverviewPage() {
  const { key } = useMkc()
  const navigate = useNavigate()
  const s = useQuery(() => status(), [key], key)
  const c = useQuery(() => listContradictions(), [key], key)

  if (s.loading && c.loading) return <Spinner label="Loading overview…" />
  if (s.error && c.error)
    return (
      <StateMessage
        title="Could not load the overview"
        detail={s.error}
        tone="danger"
        action={<button type="button" onClick={() => { s.reload(); c.reload() }} className="rounded border border-line px-3 py-1.5 text-sm hover:border-faint/60">Retry</button>}
      />
    )
  const statusData = s.data
  if (!statusData)
    return <StateMessage title="Could not load the overview" detail={s.error ?? 'No status data returned'} tone="danger" action={<button type="button" onClick={s.reload} className="rounded border border-line px-3 py-1.5 text-sm hover:border-faint/60">Retry</button>} />

  const byType = Object.entries(statusData.by_type).sort((a, b) => b[1] - a[1])
  const lifecycleData = LIFECYCLE_STATES.map((st) => ({ label: st, value: statusData.by_lifecycle_state[st] ?? 0 })).filter((d) => d.value > 0)
  const activity = statusData.recent_activity ?? []
  const activityValues = activity.map((a) => {
    const d = new Date(a.at ?? 0)
    const h = d.getHours()
    return `T${String(h).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  })
  const flagged = (c.data ?? []).filter((x) => x.status === 'flagged')
  const topTypes = byType.slice(0, 8)

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle={
          <span>
            <span className="font-mono">{statusData.knowledge_objects_total}</span> objects · {byType.length} types ·{' '}
            {statusData.sources ?? '—'} sources · last ingest <span className="font-mono">{fmtDate(statusData.last_ingest)}</span>
          </span>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">Lifecycle distribution</h3>
          {lifecycleData.length > 0 ? (
            <BarChart data={lifecycleData} ariaLabel="Knowledge objects per lifecycle state" />
          ) : (
            <p className="text-sm text-faint">No lifecycle data.</p>
          )}
        </Card>
        <Card className="p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">Types ({byType.length})</h3>
          {topTypes.length > 0 ? (
            <ul className="space-y-1.5">
              {topTypes.map(([t, n]) => (
                <li key={t} className="flex items-center justify-between gap-3 text-sm">
                  <button type="button" onClick={() => navigate('/knowledge')} className="font-mono text-accent hover:underline">
                    {t}
                  </button>
                  <span className="flex items-center gap-2">
                    <span className="h-1.5 w-24 overflow-hidden rounded-full bg-raised" aria-hidden="true">
                      <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(4, (n / (topTypes[0]?.[1] ?? 1)) * 100)}%` }} />
                    </span>
                    <span className="w-8 text-right font-mono text-xs text-muted">{n}</span>
                  </span>
                </li>
              ))}
              {byType.length > topTypes.length && <li className="text-xs text-faint">+ {byType.length - topTypes.length} more types…</li>}
            </ul>
          ) : (
            <p className="text-sm text-faint">No type data.</p>
          )}
        </Card>
        <Card className="p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">Recent activity</h3>
          {activity.length > 0 ? (
            <div>
              <ul className="space-y-2">
                {activity.slice(0, 8).map((a) => (
                  <li key={a.id} className="flex items-baseline gap-3 text-sm">
                    <span className="w-24 shrink-0 text-right font-mono text-xs text-faint">{fmtAuditTime(a.at)}</span>
                    <span className="min-w-0">
                      <span className="font-mono text-xs text-accent">{a.action}</span>
                      <span className="text-muted"> · {a.actor} · </span>
                      <span className="font-mono text-xs text-faint">{a.object_id}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-4">
                <Sparkline values={activity.map(() => 1)} suffix={activity.length > 0 ? `activity ${activity[activity.length - 1].at ? fmtAuditTime(activity[activity.length - 1].at) : ''}` : ''} ariaLabel="Recent activity timeline" />
              </div>
            </div>
          ) : (
            <p className="text-sm text-faint">No recent activity recorded.</p>
          )}
        </Card>
        <Card className="p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">Open contradictions</h3>
          {c.error && <p className="text-sm text-danger">{c.error}</p>}
          {!c.error && flagged.length > 0 && (
            <ul className="space-y-3">
              {flagged.map((f) => (
                <li key={f.id}>
                  <div className="flex items-center gap-2">
                    <Badge tone="danger">{f.severity}</Badge>
                    <Badge tone="danger">{f.status}</Badge>
                    <span className="font-mono text-xs text-faint">{f.id}</span>
                  </div>
                  <p className="mt-1.5 text-sm">
                    <span className="font-mono text-xs">{f.claim_a_id}</span>
                    <span className="text-faint"> vs </span>
                    <span className="font-mono text-xs">{f.claim_b_id}</span>
                  </p>
                  <p className="mt-1 text-xs text-muted">{f.explanation}</p>
                </li>
              ))}
            </ul>
          )}
          {!c.error && flagged.length === 0 && !c.loading && (
            <p className="text-sm text-faint">
              No flagged contradictions.
              {c.data ? ` ${c.data.length} recorded total.` : ''}
            </p>
          )}
          {c.loading && <Spinner label="Loading contradictions…" />}
        </Card>
      </div>
      {statusData.knowledge_objects_total > 0 && (
        <Card className="mt-4 p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">State mix</h3>
          <div className="flex flex-wrap gap-2">
            {lifecycleData.map((d) => (
              <Badge key={d.label} tone={lifecycleTone(d.label)}>
                {d.label}: {d.value} ({pct(d.value / statusData.knowledge_objects_total)})
              </Badge>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
