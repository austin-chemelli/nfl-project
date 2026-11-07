/**
 * What was expected of a team on each tendency, and what it's doing (ADR 0022). One row per measure on the
 * league's scale, 0 to 100% of teams: the expected range as a band, a hollow dot at expected, a filled
 * team-color dot at so far, a small tick at the team's last season. A rough guess draws a dashed band, so
 * the difference doesn't rest on shade alone. Nothing here is good or bad, so no red or green. Values print at the row end.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type ExpectRowData = {
  key: string
  label: ReactNode
  /** Plain words for the row's accessible summary. */
  summary: string
  expected: number | null
  miss: number | null
  rough: boolean
  observed: number | null
  last: number | null
  /** Printed at the row end. */
  value: ReactNode
  sub: ReactNode
  /** The scale's ends, when they aren't less and more. */
  ends?: [string, string]
  tip?: ReactNode
}

const VALUE_W = 78
const ROW_H = 54
const TRACK_Y = 34
const clamp = (v: number) => Math.min(1, Math.max(0, v))

export function ExpectRow({ rows, color = 'var(--text-secondary)', ring = 'var(--surface-1)' }: { rows: ExpectRowData[]; color?: string; ring?: string }) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const x = scaleLinear().domain([0, 1]).range([8, Math.max(60, width - VALUE_W - 12)])
  const h = rows.length * ROW_H

  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={h} role="img" aria-label={rows.map((r) => r.summary).join('; ')} className="block text-[12px]">
          {rows.map((r, i) => {
            const top = i * ROW_H
            const cy = top + TRACK_Y
            const ranged = r.expected != null && r.miss != null
            const lo = ranged ? x(clamp(r.expected! - r.miss!)) : 0
            const hi = ranged ? x(clamp(r.expected! + r.miss!)) : 0
            return (
              <g key={r.key} {...(r.tip ? bind(r.key) : {})}>
                <rect x={0} y={top} width={width} height={ROW_H} rx={4} fill={at?.key === r.key ? 'var(--surface-2)' : 'transparent'} />
                <foreignObject x={8} y={top + 2} width={Math.max(40, width - VALUE_W - 20)} height={22}>
                  <div className="truncate text-[13px] text-ink-2">{r.label}</div>
                </foreignObject>
                <line x1={x(0)} x2={x(1)} y1={cy} y2={cy} stroke="var(--border)" />
                <line x1={x(0.5)} x2={x(0.5)} y1={cy - 6} y2={cy + 6} stroke="var(--text-muted)" />
                {ranged && (
                  <rect
                    data-testid="expected-range"
                    x={lo}
                    y={cy - 6}
                    width={Math.max(2, hi - lo)}
                    height={12}
                    rx={3}
                    fill={r.rough ? 'var(--band)' : 'var(--band-strong)'}
                    stroke={r.rough ? 'var(--text-muted)' : 'none'}
                    strokeDasharray={r.rough ? '3 3' : undefined}
                  />
                )}
                {r.last != null && <line data-testid="last-season" x1={x(clamp(r.last))} x2={x(clamp(r.last))} y1={cy - 9} y2={cy + 9} stroke="var(--text-secondary)" strokeWidth={2} />}
                {r.expected != null && <circle data-testid="expected-dot" cx={x(clamp(r.expected))} cy={cy} r={5} fill="var(--surface-1)" stroke="var(--text-secondary)" strokeWidth={2} />}
                {r.observed != null && <circle data-testid="so-far-dot" cx={x(clamp(r.observed))} cy={cy} r={6} fill={color} stroke={ring} strokeWidth={2} />}
                {r.ends && (
                  <>
                    <text x={x(0)} y={cy + 17} fontSize={10} className="fill-[var(--text-muted)]">{r.ends[0]}</text>
                    <text x={x(1)} y={cy + 17} fontSize={10} textAnchor="end" className="fill-[var(--text-muted)]">{r.ends[1]}</text>
                  </>
                )}
                <text x={width - 2} y={top + 24} textAnchor="end" fontWeight={600} className="tabular fill-[var(--text-primary)]">{r.value}</text>
                <text x={width - 2} y={top + 39} textAnchor="end" fontSize={11} className="tabular fill-[var(--text-muted)]">{r.sub}</text>
              </g>
            )
          })}
        </svg>
        {card(rows.find((r) => r.key === at?.key)?.tip)}
      </div>
    </div>
  )
}
