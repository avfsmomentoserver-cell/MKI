import { useEffect, useState } from 'react'
import { listKnowledge } from '../lib/api'
import { KNOWLEDGE_TYPES, LIFECYCLE_STATES } from '../lib/constants'
import { toProvenanceView } from '../lib/types'
import { fmtDate, pct } from '../lib/format'
import { useMkc, useQuery } from '../state'
import { KnowledgeDrawer } from '../components/KnowledgeDrawer'
import { Badge, Button, Card, Input, PageHeader, Pagination, ProvenanceInline, Select, Spinner, StateMessage, lifecycleTone } from '../components/ui'

const PAGE_SIZE = 20

export function KnowledgePage() {
  const { key } = useMkc()
  const [type, setType] = useState('')
  const [state, setState] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)

  // Debounce the free-text filter.
  const [debouncedQ, setDebouncedQ] = useState('')
  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedQ(q)
      setPage(1)
    }, 250)
    return () => window.clearTimeout(t)
  }, [q])
  const resetPage = (fn: () => void) => {
    fn()
    setPage(1)
  }

  const query = useQuery(
    () =>
      listKnowledge({
        type: type || undefined,
        lifecycle_state: state || undefined,
        q: debouncedQ || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [key, type, state, debouncedQ, page],
    key,
  )
  const items = query.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="Knowledge"
        subtitle={
          query.data ? (
            <span>
              <span className="font-mono">{query.data.total}</span> objects
              {type && <span> · type <Badge tone="accent">{type}</Badge></span>}
              {state && <span> · state <Badge tone={lifecycleTone(state)}>{state}</Badge></span>}
              {debouncedQ && <span> · matching “{debouncedQ}”</span>}
            </span>
          ) : undefined
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input
          className="w-56"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by title / summary…"
          aria-label="Filter knowledge objects by text"
        />
        <Select
          value={type}
          onChange={(e) => resetPage(() => setType(e.target.value))}
          aria-label="Filter by type"
        >
          <option value="">All types</option>
          {KNOWLEDGE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <Select
          value={state}
          onChange={(e) => resetPage(() => setState(e.target.value))}
          aria-label="Filter by lifecycle state"
        >
          <option value="">All states</option>
          {LIFECYCLE_STATES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
        {(type || state || debouncedQ) && (
          <Button
            onClick={() => {
              setType('')
              setState('')
              setQ('')
              setPage(1)
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {query.loading && <Spinner label="Loading knowledge objects…" />}
      {!query.loading && query.error && (
        <StateMessage title="Could not load knowledge" detail={query.error} tone="danger" action={<Button onClick={query.reload}>Retry</Button>} />
      )}
      {!query.loading && !query.error && items.length === 0 && (
        <StateMessage
          title="No knowledge objects match"
          detail="Adjust the type, lifecycle-state or text filters."
          action={<Button onClick={query.reload}>Reset</Button>}
        />
      )}
      {!query.loading && !query.error && items.length > 0 && (
        <Card>
          <ul className="divide-y divide-line">
            {items.map((ko) => {
              const pv = toProvenanceView(ko.provenance)
              return (
                <li key={ko.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(ko.id)}
                    className="block w-full px-4 py-3 text-left transition-colors hover:bg-raised/60 focus-visible:bg-raised/60"
                  >
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{ko.title}</span>
                      <Badge tone="accent">{ko.type}</Badge>
                      <Badge tone={lifecycleTone(ko.lifecycle_state)}>{ko.lifecycle_state}</Badge>
                      <span className="w-12 text-right font-mono text-xs text-muted" title="confidence">
                        {pct(ko.confidence)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-4">
                      <span className="truncate text-xs text-muted">{ko.content_summary}</span>
                      <span className="flex shrink-0 items-center gap-3 text-xs text-faint">
                        <ProvenanceInline p={pv} />
                        <span className="font-mono">{fmtDate(ko.updated_at)}</span>
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
          <Pagination page={query.data?.page ?? 1} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onChange={setPage} />
        </Card>
      )}

      {selected && <KnowledgeDrawer id={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
