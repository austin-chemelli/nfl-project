/**
 * Every sportsbook's number on one line (ADR 0024, M20.13): a dot per book, books on the same number
 * stacked, the median as a tick, and labelled gridlines. With `sides`, each side of pick'em wears its
 * team's tint and the key numbers (3, 7, pick'em) are drawn darker, so a spread that straddles one shows.
 * The scale is the same zoom as `LinePath`, so a half-point gap is visible. Hovering a stack lists its books.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { TipRow, TipTitle, useChartTip } from './ChartTip'
import { gridTicks, valueDomain, type PathSides } from './LinePath'
import { useWidth } from './useWidth'

export type StripDot = { key: string; v: number; label: string; detail?: string }

const PAD = { left: 36, right: 36 } // room for a centred "DET −7.5" at either end
const R = 5
const STEP = 12 // px between stacked dots
const KEYS = [-7, -3, 0, 3, 7]

export function BookStrip({ dots, median, format, label, sides }: {
  dots: StripDot[]
  median: number | null
  format: (v: number) => string
  label: string
  sides?: PathSides
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  if (dots.length === 0) return null
  const stacks = new Map<number, StripDot[]>()
  for (const d of [...dots].sort((a, b) => a.v - b.v)) stacks.set(d.v, [...(stacks.get(d.v) ?? []), d])
  const tallest = Math.max(...[...stacks.values()].map((s) => s.length))
  const top = 20
  const base = top + 8 + tallest * STEP // the lowest dot's centre
  const axis = base + R + 6
  const H = axis + 16
  const vd = valueDomain(dots.map((d) => d.v), median, !!sides)
  const x = scaleLinear().domain(vd).range([PAD.left, Math.max(PAD.left + 40, width - PAD.right)])
  const [x0, x1] = [x(vd[0]), x(vd[1])]
  const ticks = gridTicks(vd)
  const keys = sides ? KEYS.filter((k) => k > vd[0] && k < vd[1]) : []
  const zx = x(0)
  const zeroIn = !!sides && vd[0] < 0 && vd[1] > 0
  const tint = (c: string) => `color-mix(in srgb, ${c} 12%, transparent)`
  const tip: ReactNode = (() => {
    const s = at ? stacks.get(Number(at.key)) : undefined
    return s ? (<><TipTitle>{format(s[0].v)}</TipTitle>{s.map((d) => <TipRow key={d.key} value={d.detail ?? ''} label={d.label} />)}</>) : null
  })()
  const spread = [...stacks.keys()]
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={H} role="img" aria-label={`${label}: ${spread.map((v) => `${format(v)} at ${stacks.get(v)!.length}`).join(', ')}${median == null ? '' : `; median ${format(median)}`}`} className="block text-[11px]">
          <text x={4} y={12} fontWeight={600} className="fill-[var(--text-secondary)]">{label}</text>
          {sides && (zeroIn ? (
            <>
              <rect x={x0} y={top} width={Math.max(0, zx - x0)} height={axis - top} fill={tint(sides.belowColor)} />
              <rect x={zx} y={top} width={Math.max(0, x1 - zx)} height={axis - top} fill={tint(sides.aboveColor)} />
            </>
          ) : (
            <rect x={x0} y={top} width={Math.max(0, x1 - x0)} height={axis - top} fill={tint(vd[0] >= 0 ? sides.aboveColor : sides.belowColor)} />
          ))}
          {ticks.map((v) => (
            <g key={v}>
              <line x1={x(v)} x2={x(v)} y1={top} y2={axis} stroke="var(--border)" />
              <text x={x(v)} y={axis + 12} textAnchor="middle" className="tabular fill-[var(--text-muted)]">{format(v)}</text>
            </g>
          ))}
          {keys.map((k) => (
            <line key={`k${k}`} data-testid="key-number" x1={x(k)} x2={x(k)} y1={top} y2={axis} stroke="var(--text-muted)" strokeWidth={1.5} />
          ))}
          <line x1={x0} x2={x1} y1={axis} y2={axis} stroke="var(--border)" />
          {median != null && (
            <g>
              <line x1={x(median)} x2={x(median)} y1={top - 2} y2={axis} stroke="var(--text-primary)" strokeOpacity={0.55} strokeDasharray="4 3" strokeWidth={1.5} />
              <text x={x(median)} y={top - 5} textAnchor="middle" className="fill-[var(--text-secondary)]">median</text>
            </g>
          )}
          {spread.map((v) => {
            const s = stacks.get(v)!
            const fill = !sides ? 'var(--text-secondary)' : v > 0 ? sides.aboveColor : v < 0 ? sides.belowColor : 'var(--text-secondary)'
            return (
              <g key={v} {...bind(String(v))}>
                <rect x={x(v) - R - 3} y={base - (s.length - 1) * STEP - R - 3} width={2 * R + 6} height={(s.length - 1) * STEP + 2 * R + 6} fill="transparent" />
                {s.map((d, i) => (
                  <circle key={d.key} cx={x(v)} cy={base - i * STEP} r={R} fill={fill} stroke="var(--surface-1)" strokeWidth={1.5} />
                ))}
              </g>
            )
          })}
        </svg>
        {card(tip)}
      </div>
    </div>
  )
}
