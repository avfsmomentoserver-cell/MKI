import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getKnowledge } from '../lib/api'
import type { KnowledgeDetail } from '../lib/types'
import { toProvenanceView } from '../lib/types'
import { fmtDateTime, pct, shortHash } from '../lib/format'
import { Drawer } from './Drawer'
import { Badge, ProvenanceInline, Spinner, StateMessage, lifecycleTone } from './ui'

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex gap-3 border-b border-line/60 py-1.5 text-sm last:border-0">
      <dt className="w-36 shrink-0 text-faint">{k}</dt>
      <dd className="min-w-0 break-words">{v}</dd>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">{title}</h3>
      {children}
    </section>
  )
}

/** Detail drawer for one knowledge object: body, lifecycle, confidence and
 *  the full provenance chain (object provenance + the source it came from). */
export function KnowledgeDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const [data, setData] = useState<KnowledgeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let stale = false
    setLoading(true)
    setError(null)
    getKnowledge(id)
      .then((d) => {
        if (!stale) setData(d)
      })
      .catch((e: unknown) => {
        if (!stale) setError(e instanceof Error ? e.message : 'Failed to load knowledge object')
      })
      .finally(() => {
        if (!stale) setLoading(false)
      })
    return () => {
      stale = true
    }
  }, [id, tick])

  const pv = data ? toProvenanceView(data.provenance) : null
  const source = data?.source ?? null
  const chain = data?.provenance_chain ?? null

  return (
    <Drawer
      title={data?.title ?? id}
      subtitle={
        data ? (
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{data.id}</span>
            <Badge tone="accent">{data.type}</Badge>
            <Badge tone={lifecycleTone(data.lifecycle_state)}>{data.lifecycle_state}</Badge>
          </span>
        ) : undefined
      }
      onClose={onClose}
    >
      {loading && <Spinner label="Loading object…" />}
      {!loading && error && (
        <StateMessage title="Could not load this object" detail={error} tone="danger" action={<button type="button" onClick={() => setTick((t) => t + 1)} className="rounded border border-line px-3 py-1.5 text-sm hover:border-faint/60">Retry</button>} />
      )}
      {!loading && !error && data && (
        <div>
          <Section title="Summary">
            <p className="text-sm text-muted">{data.content_summary}</p>
          </Section>
          <Section title="Body">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{data.body}</p>
          </Section>
          <Section title="Metadata">
            <dl>
              <Row k="confidence" v={<span className="font-mono">{pct(data.confidence)}</span>} />
              <Row k="status" v={data.status} />
              <Row k="created" v={<span className="font-mono">{fmtDateTime(data.created_at)}</span>} />
              <Row k="updated" v={<span className="font-mono">{fmtDateTime(data.updated_at)}</span>} />
              <Row k="source" v={source ? <span className="font-mono">{source.id}</span> : <span className="text-faint">none</span>} />
            </dl>
          </Section>
          <Section title="Provenance">
            <dl>
              <Row
                k="source type"
                v={
                  <span className="flex items-center gap-2">
                    <Badge tone="neutral">{pv?.source_type ?? '—'}</Badge>
                    {pv?.extraction_method && <span className="font-mono text-xs text-faint">{pv.extraction_method}</span>}
                  </span>
                }
              />
              <Row k="location" v={<span className="font-mono text-xs">{pv?.file_path ?? '—'}</span>} />
              <Row k="commit" v={pv?.commit_hash ? <span className="font-mono text-xs">{shortHash(pv.commit_hash, 12)}</span> : '—'} />
              <Row k="author" v={pv?.author ?? '—'} />
              <Row k="date" v={<span className="font-mono text-xs">{pv?.date ?? '—'}</span>} />
              {pv?.original_text && (
                <Row
                  k="original text"
                  v={<blockquote className="border-l-2 border-line pl-2 text-xs italic text-muted">{pv.original_text}</blockquote>}
                />
              )}
            </dl>
          </Section>
          {source && (
            <Section title="Source record">
              <dl>
                <Row k="type" v={<Badge tone="neutral">{source.source_type}</Badge>} />
                <Row k="source id" v={<span className="font-mono text-xs">{source.source_id}</span>} />
                <Row k="path" v={<span className="font-mono text-xs">{source.path}</span>} />
                <Row k="indexed" v={<span className="font-mono text-xs">{fmtDateTime(source.indexed_at)}</span>} />
              </dl>
            </Section>
          )}
          {chain && (
            <Section title="Provenance chain">
              <p className="text-xs text-muted">
                {toProvenanceView(chain.object).source_type ?? 'object'} → {chain.source ? <span className="font-mono">{chain.source.path}</span> : <span className="text-faint">unresolved source</span>}
              </p>
              <div className="mt-1.5">
                <ProvenanceInline p={toProvenanceView(chain.object)} />
              </div>
            </Section>
          )}
        </div>
      )}
    </Drawer>
  )
}
