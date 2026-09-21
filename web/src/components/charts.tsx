/** Hand-rolled inline SVG charts. No charting library (project rule). */

export interface BarDatum {
  label: string
  value: number
}

export function BarChart({ data, ariaLabel }: { data: BarDatum[]; ariaLabel: string }) {
  const max = data.reduce((m, d) => Math.max(m, d.value), 0)
  const hasBars = max > 0
  return (
    <div>
      <svg
        viewBox="0 0 100 40"
        preserveAspectRatio="none"
        className="h-28 w-full"
        role="img"
        aria-label={ariaLabel}
      >
        {data.map((d, i) => {
          const w = 100 / data.length
          const barW = Math.max(0.5, w * 0.62)
          const h = hasBars ? (d.value / max) * 34 : 0
          return (
            <rect
              key={`${d.label}-${i}`}
              x={i * w + (w - barW) / 2}
              y={38 - h}
              width={barW}
              height={h}
              rx={0.4}
              fill="var(--color-accent)"
              opacity={0.9}
            />
          )
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {data.map((d, i) => (
          <span key={`${d.label}-legend-${i}`} className="flex items-center gap-1 text-[11px] text-muted">
            <span className="size-2 rounded-[2px] bg-accent" aria-hidden="true" />
            {d.label}
            <span className="font-mono text-faint">{d.value}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function Sparkline({
  values,
  ariaLabel,
  height = 48,
  suffix,
}: {
  values: number[]
  ariaLabel: string
  height?: number
  suffix?: string
}) {
  const W = 100
  const H = 40
  const max = values.length > 0 ? Math.max(...values) : 1
  const min = values.length > 0 ? Math.min(...values) : 0
  const range = max - min || 1
  const step = values.length > 1 ? W / (values.length - 1) : W
  const pts = values
    .map((v, i) => `${(i * step).toFixed(2)},${(H - ((v - min) / range) * (H - 4) - 2).toFixed(2)}`)
    .join(' ')
  const total = values.reduce((a, b) => a + b, 0)
  const last = values.length > 0 ? values[values.length - 1] : 0
  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        style={{ height }}
        className="w-full"
        role="img"
        aria-label={ariaLabel}
      >
        {values.length > 1 && (
          <polyline
            points={pts}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={1.2}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {values.length > 0 && (
          <circle
            cx={(values.length - 1) * step}
            cy={H - ((last - min) / range) * (H - 4) - 2}
            r={1.6}
            fill="var(--color-accent)"
          />
        )}
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[11px] text-faint">
        <span>{suffix ?? ''}</span>
        <span>
          {total} total · last {last}
        </span>
      </div>
    </div>
  )
}
