/**
 * Both teams on one league band, one metric per row on its own scale. The band shows how the league
 * is spread: faint from p10 to p90, solid over the middle half where teams bunch up, a tick at the
 * median. Rows flagged `stands` draw the gap between the two dots at full strength; the rest are
 * muted, so the page reads as "these few gaps matter" rather than a wall of numbers. `flip` reverses
 * a row where lower is better, so right is always the better side.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type MatchupBandRow = {
  key: string
  label: ReactNode
  away: number
  home: number
  lo: number
  q1: number
  med: number
  q3: number
  hi: number
  stands: boolean
  flip?: boolean
  help?: string
}

const AWAY = 'var(--team-away)'
const HOME = 'var(--team-home)'
const VALUE_W = 96

export function MatchupBand({ rows, away, home, format, labelWidth = 220 }: {
  rows: MatchupBandRow[]
  away: string
  home: string
  format: (v: number, key: string) => string
  labelWidth?: number
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  // on a phone the label takes its own line above the band, or nearly every name is cut off
  const narrow = width < 480
  const rowHeight = narrow ? 50 : 36
  const lw = narrow ? width - VALUE_W : labelWidth
  const x0 = narrow ? 2 : lw + 8
  const x1 = Math.max(x0 + 40, width - VALUE_W - 8)
  const h = rows.length * rowHeight + 4
  const hovered = rows.find((r) => r.key === at?.key)
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={h} role="img" aria-label={rows.map((r) => `${plain(r.label)}: ${away} ${format(r.away, r.key)}, ${home} ${format(r.home, r.key)}${r.stands ? ', a big gap' : ''}`).join('; ')} className="block text-[12px]">
          {rows.map((r, i) => {
            const top = i * rowHeight
            const cy = narrow ? top + 31 : top + rowHeight / 2
            const vals = [r.away, r.home, r.lo, r.hi]
            const lo = Math.min(...vals)
            const hi = Math.max(...vals)
            const pad = (hi - lo) * 0.08 || 1
            const x = scaleLinear().domain(r.flip ? [hi + pad, lo - pad] : [lo - pad, hi + pad]).range([x0, x1])
            const span = (a: number, b: number) => ({ x: Math.min(x(a), x(b)), width: Math.max(2, Math.abs(x(b) - x(a))) })
            const op = r.stands ? 1 : 0.75
            const on = hovered?.key === r.key
            return (
              <g key={r.key} data-stands={r.stands || undefined} {...bind(r.key)}>
                <rect x={0} y={top} width={width} height={rowHeight} rx={4} fill={on ? 'var(--surface-2)' : 'transparent'} />
                <foreignObject x={0} y={top} width={lw} height={narrow ? 20 : rowHeight}>
                  <div className={`flex h-full items-center truncate text-[13px] ${r.stands || on ? 'font-medium text-ink' : 'text-ink-3'}`}>{r.label}</div>
                </foreignObject>
                <rect data-testid="band" {...span(r.lo, r.hi)} y={cy - 7} height={14} rx={3} fill="var(--band)" />
                <rect data-testid="band-core" {...span(r.q1, r.q3)} y={cy - 7} height={14} fill="var(--band-strong)" />
                <line x1={x(r.med)} x2={x(r.med)} y1={cy - 9} y2={cy + 9} stroke="var(--text-muted)" strokeWidth={1.5} />
                {r.stands && <line x1={x(r.away)} x2={x(r.home)} y1={cy} y2={cy} stroke="var(--text-primary)" strokeWidth={2} />}
                <circle cx={x(r.away)} cy={cy} r={6} fill={AWAY} stroke="var(--surface-1)" strokeWidth={2} opacity={on ? 1 : op} />
                <circle cx={x(r.home)} cy={cy} r={6} fill={HOME} stroke="var(--surface-1)" strokeWidth={2} opacity={on ? 1 : op} />
                <text x={width - 2} y={cy - 3} textAnchor="end" fontWeight={r.stands ? 600 : 400} className="tabular fill-[var(--text-secondary)]">{away} {format(r.away, r.key)}</text>
                <text x={width - 2} y={cy + 12} textAnchor="end" fontWeight={r.stands ? 600 : 400} className="tabular fill-[var(--text-secondary)]">{home} {format(r.home, r.key)}</text>
              </g>
            )
          })}
        </svg>
        {card(
          hovered && (
            <>
              <TipTitle note={hovered.help}>{hovered.label}</TipTitle>
              <TipRow color={AWAY} value={format(hovered.away, hovered.key)} label={away} />
              <TipRow color={HOME} value={format(hovered.home, hovered.key)} label={home} />
              <TipNote>
                League median {format(hovered.med, hovered.key)}. Half of teams sit between {format(hovered.q1, hovered.key)} and {format(hovered.q3, hovered.key)}, most between {format(hovered.lo, hovered.key)} and {format(hovered.hi, hovered.key)}.
                {hovered.stands && <span className="text-ink-2"> A big gap: wider than the league's middle half.</span>}
              </TipNote>
            </>
          ),
        )}
      </div>
    </div>
  )
}

function plain(label: ReactNode): string {
  return typeof label === 'string' || typeof label === 'number' ? String(label) : 'metric'
}
