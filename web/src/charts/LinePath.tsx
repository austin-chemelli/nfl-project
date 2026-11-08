/**
 * One market measure over the week before kickoff (ADR 0024): a step line through each pre-kickoff
 * snapshot (a line holds until the next one), dashed verticals at the locks, numbered event marks on
 * the time axis that match the list under the chart, and an optional dashed reference line (our own
 * number). With `sides`, the scale always includes zero: the pick'em line splits the plot into two
 * bands tinted with each team's color and labelled with who is favored there (Austin, 2026-11-07).
 * The first and latest values print at the ends, so nothing needs hover; hovering a point shows its
 * time and books.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { TipRow, TipTitle, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type PathPoint = { t: number; v: number | null; note: string }
export type PathMark = { t: number; label: string }
export type PathEvent = { t: number; n: number }
/** Above zero is `above` (the home team, spread > 0); below is `below`. Colors are CSS values. */
export type PathSides = { above: string; below: string; aboveColor: string; belowColor: string }
export type PathRef = { v: number; label: string }

const H = 150
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
const PAD = { top: 16, right: 64, bottom: 24, left: 76 }

/** The value range to draw: the data, the reference, zero when sides are shown, padded so each side
 * of zero keeps a band tall enough for its label. */
// oxlint-disable-next-line react/only-export-components
export function valueDomain(vals: number[], ref: number | null, zero: boolean): [number, number] {
  const all = [...vals, ...(ref == null ? [] : [ref]), ...(zero ? [0] : [])]
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const pad = Math.max(zero ? 1.5 : 0.5, (hi - lo) * 0.12)
  return [lo - pad, hi + pad]
}

export function LinePath({ points, marks = [], events = [], format, up, down, label, domain, sides, reference }: {
  points: PathPoint[]
  marks?: PathMark[]
  events?: PathEvent[]
  format: (v: number) => string
  /** Words for the top and bottom of the scale when there are no sides, e.g. "higher" and "lower". */
  up?: string
  down?: string
  label: string
  /** The shared time span, so stacked charts line up. */
  domain: [number, number]
  sides?: PathSides
  reference?: PathRef | null
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const vals = points.flatMap((p) => (p.v == null ? [] : [p.v]))
  if (vals.length === 0) return null
  const x = scaleLinear().domain(domain).range([PAD.left, Math.max(PAD.left + 40, width - PAD.right)])
  const y = scaleLinear().domain(valueDomain(vals, reference?.v ?? null, !!sides)).range([H - PAD.bottom, PAD.top])
  const seen = points.filter((p) => p.v != null) as (PathPoint & { v: number })[]
  let d = ''
  seen.forEach((p, i) => {
    d += i === 0 ? `M${x(p.t)},${y(p.v)}` : `H${x(p.t)}V${y(p.v)}`
  })
  const first = seen[0]
  const last = seen[seen.length - 1]
  const [x0, x1] = [x(domain[0]), x(domain[1])]
  const top = PAD.top
  const bottom = H - PAD.bottom
  const zy = y(0)
  const dotColor = (v: number) => (!sides ? 'var(--surface-1)' : v > 0 ? sides.aboveColor : v < 0 ? sides.belowColor : 'var(--surface-1)')
  const refY = reference ? y(reference.v) : null
  // the reference label sits above its line, or below when the first value's label is in the way
  const refLabelY = refY == null ? 0 : Math.abs(refY - (y(first.v) - 8)) < 14 ? refY + 12 : refY - 4
  const tip: ReactNode = (() => {
    const p = seen.find((q) => String(q.t) === at?.key)
    return p ? (<><TipTitle note={p.note}>{label}</TipTitle><TipRow value={format(p.v)} label="consensus" /></>) : null
  })()
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={H} role="img" aria-label={`${label}: ${format(first.v)} at first, ${format(last.v)} latest${reference ? `; ${reference.label}` : ''}`} className="block text-[11px]">
          <text x={4} y={top - 4} fontWeight={600} className="fill-[var(--text-secondary)]">{label}</text>
          {sides ? (
            <>
              <rect x={x0} y={top} width={Math.max(0, x1 - x0)} height={Math.max(0, zy - top)} fill={`color-mix(in srgb, ${sides.aboveColor} 12%, transparent)`} />
              <rect x={x0} y={zy} width={Math.max(0, x1 - x0)} height={Math.max(0, bottom - zy)} fill={`color-mix(in srgb, ${sides.belowColor} 12%, transparent)`} />
              <line x1={x0} x2={x1} y1={zy} y2={zy} stroke="var(--text-muted)" />
              {Math.abs(zy - (y(last.v) - 8)) > 12 && <text x={x1 + 4} y={zy + 3.5} className="fill-[var(--text-muted)]">pick&apos;em</text>}
              <text x={4} y={Math.min((top + zy) / 2 + 4, zy - 3)} className="fill-[var(--text-secondary)]">{sides.above} favored</text>
              <text x={4} y={Math.max((zy + bottom) / 2 + 4, zy + 12)} className="fill-[var(--text-secondary)]">{sides.below} favored</text>
            </>
          ) : (
            <>
              {up && <text x={4} y={top + 10} className="fill-[var(--text-muted)]">{up}</text>}
              {down && <text x={4} y={bottom} className="fill-[var(--text-muted)]">{down}</text>}
            </>
          )}
          <line x1={x0} x2={x1} y1={bottom + 8} y2={bottom + 8} stroke="var(--border)" />
          {marks.map((m) => (
            <g key={`${m.label}-${m.t}`}>
              <line x1={x(m.t)} x2={x(m.t)} y1={top} y2={bottom + 8} stroke="var(--text-muted)" strokeDasharray="3 3" />
              <text x={x(m.t) + 3} y={top + 9} className="fill-[var(--text-muted)]">{m.label}</text>
            </g>
          ))}
          {reference && refY != null && (
            <g>
              <line x1={x0} x2={x1} y1={refY} y2={refY} stroke="var(--text-primary)" strokeOpacity={0.55} strokeDasharray="6 4" strokeWidth={1.5} />
              <text x={x0 + 4} y={refLabelY} className="fill-[var(--text-secondary)]">{reference.label}</text>
            </g>
          )}
          <path d={d} fill="none" stroke="var(--text-secondary)" strokeWidth={2} />
          {seen.map((p) => (
            <g key={p.t} {...bind(String(p.t))}>
              <circle cx={x(p.t)} cy={y(p.v)} r={9} fill="transparent" />
              <circle cx={x(p.t)} cy={y(p.v)} r={4} fill={dotColor(p.v)} stroke="var(--surface-1)" strokeWidth={2} />
              <circle cx={x(p.t)} cy={y(p.v)} r={5.5} fill="none" stroke="var(--text-secondary)" strokeWidth={1} />
            </g>
          ))}
          {stagger(events.map((e) => x(e.t))).map((row, i) => {
            const e = events[i]
            const cy = bottom + 8 - row * 15
            return (
              <g key={`${e.n}-${e.t}`} aria-hidden>
                <circle cx={x(e.t)} cy={cy} r={7} fill="var(--surface-2)" stroke="var(--text-muted)" />
                <text x={x(e.t)} y={cy + 3.5} textAnchor="middle" fontSize={9} className="fill-[var(--text-primary)]">{e.n}</text>
              </g>
            )
          })}
          <text x={x(first.t) + 8} y={y(first.v) - 8} className="tabular fill-[var(--text-secondary)]">{format(first.v)}</text>
          <text x={x(last.t) + 8} y={y(last.v) - 8} fontWeight={600} className="tabular fill-[var(--text-primary)]">{format(last.v)}</text>
        </svg>
        {card(tip)}
      </div>
    </div>
  )
}
