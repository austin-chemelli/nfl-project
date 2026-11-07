/**
 * One team's tendencies against the league (ADR 0022, revised 2026-11-07). One row per measure on the league's
 * scale, 0 to 100% of teams, with the league average as one dashed line through every row, labelled once at
 * the top, and three marks in three shapes: this season (a filled team-color dot), the play-caller's own past
 * (a hollow diamond) and the team's last season (a filled triangle).
 * A tendency isn't good or bad, so no red or green. This season's value prints at the row end.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type TendencyRowData = {
  key: string
  label: ReactNode
  /** Plain words for the row's accessible summary. */
  summary: string
  now: number | null
  past: number | null
  last: number | null
  value: ReactNode
  sub: ReactNode
  /** The scale's ends, when they aren't less and more. */
  ends?: [string, string]
  tip?: ReactNode
}

const VALUE_W = 78
const ROW_H = 54
const TRACK_Y = 34
const HEAD = 16 // room for the "League avg" label
const clamp = (v: number) => Math.min(1, Math.max(0, v))

export function TendencyRow({ rows, color = 'var(--text-secondary)' }: { rows: TendencyRowData[]; color?: string }) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const x = scaleLinear().domain([0, 1]).range([10, Math.max(60, width - VALUE_W - 14)])
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={HEAD + rows.length * ROW_H} role="img" aria-label={rows.map((r) => r.summary).join('; ')} className="block text-[12px]">
          <text x={x(0.5)} y={11} fontSize={10} textAnchor="middle" className="fill-[var(--text-muted)]">League avg</text>
          <line data-testid="league-average" x1={x(0.5)} x2={x(0.5)} y1={HEAD - 2} y2={HEAD + rows.length * ROW_H - 6} stroke="var(--text-muted)" strokeDasharray="2 4" />
          {rows.map((r, i) => {
            const top = HEAD + i * ROW_H
            const cy = top + TRACK_Y
            return (
              <g key={r.key} {...(r.tip ? bind(r.key) : {})}>
                <rect x={0} y={top} width={width} height={ROW_H} rx={4} fill={at?.key === r.key ? 'var(--surface-2)' : 'transparent'} />
                <foreignObject x={8} y={top + 2} width={Math.max(40, width - VALUE_W - 20)} height={22}>
                  <div className="text-[13px] text-ink-2">{r.label}</div>
                </foreignObject>
                <line x1={x(0)} x2={x(1)} y1={cy} y2={cy} stroke="var(--border)" strokeWidth={4} strokeLinecap="round" />
                {r.last != null && (
                  <path data-testid="last-season" d={`M ${x(clamp(r.last))} ${cy - 2} l -7 11 h 14 z`} fill="var(--text-secondary)" stroke="var(--surface-1)" strokeWidth={1.5} strokeLinejoin="round" />
                )}
                {r.past != null && (
                  <rect data-testid="caller-past" x={x(clamp(r.past)) - 5} y={cy - 5} width={10} height={10} transform={`rotate(45 ${x(clamp(r.past))} ${cy})`} fill="var(--surface-1)" stroke="var(--text-secondary)" strokeWidth={2} />
                )}
                {r.now != null && <circle data-testid="this-season" cx={x(clamp(r.now))} cy={cy} r={6} fill={color} stroke="var(--surface-1)" strokeWidth={2} />}
                {r.ends && (
                  <>
                    <text x={x(0)} y={cy + 18} fontSize={10} className="fill-[var(--text-muted)]">{r.ends[0]}</text>
                    <text x={x(1)} y={cy + 18} fontSize={10} textAnchor="end" className="fill-[var(--text-muted)]">{r.ends[1]}</text>
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
