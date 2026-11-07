/**
 * One market measure over the week before kickoff (ADR 0023): a step line through each pre-kickoff
 * snapshot (a line holds until the next one), dashed verticals at the locks, and numbered event marks
 * on the time axis that match the list printed under the chart. The first and latest values print at
 * the ends, so nothing needs hover; hovering a point shows its time and books.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { TipRow, TipTitle, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type PathPoint = { t: number; v: number | null; note: string }
export type PathMark = { t: number; label: string }
export type PathEvent = { t: number; n: number }

const H = 120
const MARK_GAP = 15 // event marks closer than this in px stagger upward

/** A row per mark (0 on the axis, 1 above, ...) so marks closer than MARK_GAP don't overlap. */
// oxlint-disable-next-line react/only-export-components
export function stagger(xs: number[]): number[] {
  const rows: number[] = []
  const lastX: number[] = []
  for (const x of xs) {
    let r = 0
    while (lastX[r] != null && x - lastX[r] < MARK_GAP) r++
    rows.push(r)
    lastX[r] = x
  }
  return rows
}
const PAD = { top: 14, right: 64, bottom: 22, left: 64 }

export function LinePath({ points, marks = [], events = [], format, up, down, label, domain }: {
  points: PathPoint[]
  marks?: PathMark[]
  events?: PathEvent[]
  format: (v: number) => string
  /** Words for the top and bottom of the scale, e.g. "toward BAL" and "toward JAX". */
  up: string
  down: string
  label: string
  /** The shared time span, so stacked charts line up. */
  domain: [number, number]
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const vals = points.flatMap((p) => (p.v == null ? [] : [p.v]))
  if (vals.length === 0) return null
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const pad = Math.max(0.5, (hi - lo) * 0.15)
  const x = scaleLinear().domain(domain).range([PAD.left, Math.max(PAD.left + 40, width - PAD.right)])
  const y = scaleLinear().domain([lo - pad, hi + pad]).range([H - PAD.bottom, PAD.top])
  const seen = points.filter((p) => p.v != null) as (PathPoint & { v: number })[]
  let d = ''
  seen.forEach((p, i) => {
    d += i === 0 ? `M${x(p.t)},${y(p.v)}` : `H${x(p.t)}V${y(p.v)}`
  })
  const first = seen[0]
  const last = seen[seen.length - 1]
  const tip: ReactNode = (() => {
    const p = seen.find((q) => String(q.t) === at?.key)
    return p ? (<><TipTitle note={p.note}>{label}</TipTitle><TipRow value={format(p.v)} label="consensus" /></>) : null
  })()
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={H} role="img" aria-label={`${label}: ${format(first.v)} at first, ${format(last.v)} latest`} className="block text-[11px]">
          <text x={4} y={PAD.top + 4} className="fill-[var(--text-muted)]">{up}</text>
          <text x={4} y={H - PAD.bottom} className="fill-[var(--text-muted)]">{down}</text>
          <line x1={x(domain[0])} x2={x(domain[1])} y1={H - PAD.bottom + 8} y2={H - PAD.bottom + 8} stroke="var(--border)" />
          {marks.map((m) => (
            <g key={`${m.label}-${m.t}`}>
              <line x1={x(m.t)} x2={x(m.t)} y1={PAD.top - 6} y2={H - PAD.bottom + 8} stroke="var(--text-muted)" strokeDasharray="3 3" />
              <text x={x(m.t) + 3} y={PAD.top - 2} className="fill-[var(--text-muted)]">{m.label}</text>
            </g>
          ))}
          <path d={d} fill="none" stroke="var(--text-secondary)" strokeWidth={2} />
          {seen.map((p) => (
            <g key={p.t} {...bind(String(p.t))}>
              <circle cx={x(p.t)} cy={y(p.v)} r={9} fill="transparent" />
              <circle cx={x(p.t)} cy={y(p.v)} r={3.5} fill="var(--surface-1)" stroke="var(--text-secondary)" strokeWidth={2} />
            </g>
          ))}
          {stagger(events.map((e) => x(e.t))).map((row, i) => {
            const e = events[i]
            const cy = H - PAD.bottom + 8 - row * 15
            return (
              <g key={`${e.n}-${e.t}`} aria-hidden>
                <circle cx={x(e.t)} cy={cy} r={7} fill="var(--surface-2)" stroke="var(--text-muted)" />
                <text x={x(e.t)} y={cy + 3.5} textAnchor="middle" fontSize={9} className="fill-[var(--text-primary)]">{e.n}</text>
              </g>
            )
          })}
          <text x={x(first.t) + 6} y={y(first.v) - 8} className="tabular fill-[var(--text-secondary)]">{format(first.v)}</text>
          <text x={x(last.t) + 4} y={y(last.v) - 8} fontWeight={600} className="tabular fill-[var(--text-primary)]">{format(last.v)}</text>
        </svg>
        {card(tip)}
      </div>
    </div>
  )
}
