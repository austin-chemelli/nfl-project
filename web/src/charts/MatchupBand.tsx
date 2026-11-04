/**
 * Both teams on one league band, one metric per row on its own scale: the league's typical range
 * (p10 to p90) as a band, a dot per team, both values printed at the row end. Rows flagged `stands`
 * draw the gap between the dots at full strength; the rest are muted, so the page reads as "these
 * few gaps matter" rather than a wall of numbers. `flip` reverses a row where lower is better, so
 * right is always the better side.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useWidth } from './useWidth'

export type MatchupBandRow = {
  key: string
  label: ReactNode
  away: number
  home: number
  lo: number
  hi: number
  stands: boolean
  flip?: boolean
  title?: string
}

const AWAY = 'var(--div-neg)'
const HOME = 'var(--div-pos)'
const VALUE_W = 96

export function MatchupBand({ rows, away, home, format, labelWidth = 220 }: {
  rows: MatchupBandRow[]
  away: string
  home: string
  format: (v: number, key: string) => string
  labelWidth?: number
}) {
  const [ref, width] = useWidth()
  // on a phone the label takes its own line above the band, or nearly every name is cut off
  const narrow = width < 480
  const rowHeight = narrow ? 50 : 36
  const lw = narrow ? width - VALUE_W : labelWidth
  const x0 = narrow ? 2 : lw + 8
  const x1 = Math.max(x0 + 40, width - VALUE_W - 8)
  const h = rows.length * rowHeight + 4
  return (
    <div ref={ref} className="w-full">
      <svg width={width} height={h} role="img" aria-label={rows.map((r) => `${plain(r.label)}: ${away} ${format(r.away, r.key)}, ${home} ${format(r.home, r.key)}${r.stands ? ', a big gap' : ''}`).join('; ')} className="block text-[12px]">
        {rows.map((r, i) => {
          const top = i * rowHeight
          const cy = narrow ? top + 31 : top + rowHeight / 2
          const vals = [r.away, r.home, r.lo, r.hi]
          const lo = Math.min(...vals)
          const hi = Math.max(...vals)
          const pad = (hi - lo) * 0.08 || 1
          const x = scaleLinear().domain(r.flip ? [hi + pad, lo - pad] : [lo - pad, hi + pad]).range([x0, x1])
          const op = r.stands ? 1 : 0.45
          return (
            <g key={r.key} data-stands={r.stands || undefined}>
              <title>{r.title ?? ''}</title>
              <foreignObject x={0} y={top} width={lw} height={narrow ? 20 : rowHeight}>
                <div className={`flex h-full items-center truncate text-[13px] ${r.stands ? 'font-medium text-ink' : 'text-ink-3'}`}>{r.label}</div>
              </foreignObject>
              <rect data-testid="band" x={Math.min(x(r.lo), x(r.hi))} y={cy - 7} width={Math.max(2, Math.abs(x(r.hi) - x(r.lo)))} height={14} rx={3} fill="var(--div-mid)" opacity={r.stands ? 1 : 0.6} />
              {r.stands && <line x1={x(r.away)} x2={x(r.home)} y1={cy} y2={cy} stroke="var(--text-secondary)" strokeWidth={2} />}
              <circle cx={x(r.away)} cy={cy} r={5.5} fill={AWAY} stroke="var(--surface-1)" strokeWidth={1.5} opacity={op} />
              <circle cx={x(r.home)} cy={cy} r={5.5} fill={HOME} stroke="var(--surface-1)" strokeWidth={1.5} opacity={op} />
              <text x={width - 2} y={cy - 3} textAnchor="end" fontWeight={r.stands ? 600 : 400} className="tabular fill-[var(--text-secondary)]">{away} {format(r.away, r.key)}</text>
              <text x={width - 2} y={cy + 12} textAnchor="end" fontWeight={r.stands ? 600 : 400} className="tabular fill-[var(--text-secondary)]">{home} {format(r.home, r.key)}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function plain(label: ReactNode): string {
  return typeof label === 'string' || typeof label === 'number' ? String(label) : 'metric'
}
