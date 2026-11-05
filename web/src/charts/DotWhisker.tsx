/**
 * Point estimates with intervals, one row each, against a reference line (default 0).
 * Used for "what history says" effects and backtest differences vs the market.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useWidth } from './useWidth'

export type DotRow = { key: string; label: ReactNode; value: number; lo: number; hi: number; color?: string; title?: string }

export function DotWhisker({ rows, format, refValue = 0, refLabel, leftLabel, rightLabel, marker, rowHeight = 26, labelWidth = 170 }: {
  rows: DotRow[]
  format: (v: number) => string
  refValue?: number
  refLabel?: string
  leftLabel?: string
  rightLabel?: string
  /** A second vertical mark, dashed, for a value worth reading rows against. */
  marker?: { value: number; label: string }
  rowHeight?: number
  labelWidth?: number
}) {
  const [ref, width] = useWidth()
  const lw = width < 480 ? Math.min(110, labelWidth) : labelWidth
  const lo = Math.min(refValue, ...rows.map((r) => r.lo))
  const hi = Math.max(refValue, ...rows.map((r) => r.hi))
  const pad = (hi - lo) * 0.08 || 1
  const x = scaleLinear().domain([lo - pad, hi + pad]).range([lw, width - 56]).nice()
  const head = 20
  const foot = marker ? 16 : 0 // the marker's label gets its own line, under the ticks
  const h = head + rows.length * rowHeight + 20 + foot
  const ticks = x.ticks(width < 480 ? 3 : 5)
  return (
    <div ref={ref} className="w-full">
      <svg width={width} height={h} role="img" className="block text-[12px]">
        <g className="fill-[var(--text-muted)]">
          {leftLabel && <text x={x(refValue) - 6} y={12} textAnchor="end">← {leftLabel}</text>}
          {rightLabel && <text x={x(refValue) + 6} y={12}>{rightLabel} →</text>}
        </g>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={head} y2={h - 18 - foot} stroke="var(--border)" strokeDasharray={t === refValue ? undefined : '2 3'} />
            <text x={x(t)} y={h - 4 - foot} textAnchor="middle" className="tabular fill-[var(--text-muted)]">{format(t)}</text>
          </g>
        ))}
        <line x1={x(refValue)} x2={x(refValue)} y1={head} y2={h - 18 - foot} stroke="var(--text-muted)">
          {refLabel && <title>{refLabel}</title>}
        </line>
        {marker && (
          <g>
            <line x1={x(marker.value)} x2={x(marker.value)} y1={head} y2={h - 18 - foot} stroke="var(--text-muted)" strokeWidth={1.5} strokeDasharray="2 3" />
            <text x={x(marker.value)} y={h - 4} textAnchor="middle" className="fill-[var(--text-muted)]">↑ {marker.label}</text>
          </g>
        )}
        {rows.map((r, i) => {
          const y = head + i * rowHeight + rowHeight / 2
          const c = r.color ?? 'var(--accent)'
          return (
            <g key={r.key}>
              <title>{r.title ?? `${format(r.value)} (${format(r.lo)} to ${format(r.hi)})`}</title>
              <foreignObject x={0} y={y - rowHeight / 2} width={lw - 8} height={rowHeight}>
                <div className="flex h-full items-center truncate text-[13px] text-ink-2">{r.label}</div>
              </foreignObject>
              <line x1={x(r.lo)} x2={x(r.hi)} y1={y} y2={y} stroke={c} strokeWidth={2} strokeLinecap="round" opacity={0.55} />
              <circle cx={x(r.value)} cy={y} r={4.5} fill={c} stroke="var(--surface-1)" strokeWidth={1.5} />
            </g>
          )
        })}
      </svg>
    </div>
  )
}
