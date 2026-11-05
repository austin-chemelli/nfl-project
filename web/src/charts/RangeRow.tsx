/**
 * One metric per row on its own scale: the league's typical range as a band (p10 to p90), the league
 * average as a tick, the team's season value as a hollow dot and this game's value as a filled dot colored
 * by `verdict`. The game value and its delta vs season are printed at the row end, so nothing needs hover.
 * Without a band (`lo`/`hi` null) the row scales to its own values and says so.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type RangeVerdict = 'better' | 'worse' | 'same' | 'neutral'
export type RangeRowData = {
  key: string
  label: ReactNode
  game: number | null
  season: number | null
  league: number | null
  lo: number | null
  hi: number | null
  verdict: RangeVerdict
  title?: string
  tip?: ReactNode
}

const VERDICT_COLOR: Record<RangeVerdict, string> = { better: 'var(--good)', worse: 'var(--critical)', same: 'var(--text-muted)', neutral: 'var(--text-muted)' }
const VALUE_W = 84
const num = (v: number | null): v is number => v != null && Number.isFinite(v)

function signed(d: number, format: (v: number) => string): string {
  return `${d < 0 ? '−' : '+'}${format(Math.abs(d))}`
}

export function RangeRow({ rows, format, formatDelta, labelWidth = 150, rowHeight = 36, legend }: {
  rows: RangeRowData[]
  format: (v: number) => string
  formatDelta?: (d: number) => string
  labelWidth?: number
  rowHeight?: number
  /** Replaces the default legend; `false` hides it. */
  legend?: ReactNode | false
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const lw = width < 480 ? Math.min(110, labelWidth) : labelWidth
  const x0 = lw + 8
  const x1 = Math.max(x0 + 40, width - VALUE_W - 8)
  const delta = formatDelta ?? ((d: number) => signed(d, format))
  const h = rows.length * rowHeight + 4

  const aria = rows
    .map((r) => {
      if (!num(r.game)) return `${plain(r.label)} no data`
      const d = num(r.season) ? `, ${delta(r.game - r.season)} vs season` : ''
      return `${plain(r.label)} ${format(r.game)}${d}`
    })
    .join('; ')

  return (
    <div ref={ref} className="w-full">
      {legend !== false &&
        (legend ?? (
          <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-[var(--text-secondary)]" /> Season</span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--good)]" />
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--critical)]" /> This game
            </span>
            <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-0.5 bg-[var(--text-muted)]" /> League average</span>
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-5 rounded-sm bg-[var(--div-mid)]" /> Typical range</span>
          </div>
        ))}
      <div ref={box} className="relative">
      <svg width={width} height={h} role="img" aria-label={aria} className="block text-[12px]">
        {rows.map((r, i) => {
          const cy = i * rowHeight + rowHeight / 2
          const bandLo = num(r.lo) && num(r.hi) ? r.lo : null
          const bandHi = num(r.lo) && num(r.hi) ? r.hi : null
          const hasBand = bandLo != null && bandHi != null
          const vals = [r.game, r.season, r.league, bandLo, bandHi].filter(num)
          const lo = vals.length ? Math.min(...vals) : 0
          const hi = vals.length ? Math.max(...vals) : 1
          const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.1 || 1
          const x = scaleLinear().domain([lo - pad, hi + pad]).range([x0, x1])
          const color = VERDICT_COLOR[r.verdict]
          const d = num(r.game) && num(r.season) ? r.game - r.season : null
          const title =
            r.title ?? `${plain(r.label)}: ${num(r.game) ? format(r.game) : 'no data'}${num(r.season) ? `, season ${format(r.season)}` : ''}${num(r.league) ? `, league ${format(r.league)}` : ''}`
          return (
            <g key={r.key} {...(r.tip ? bind(r.key) : {})}>
              {r.tip ? <rect x={0} y={i * rowHeight} width={width} height={rowHeight} rx={4} fill={at?.key === r.key ? 'var(--surface-2)' : 'transparent'} /> : <title>{title}</title>}
              <foreignObject x={0} y={cy - rowHeight / 2} width={lw} height={rowHeight}>
                <div className="flex h-full items-center truncate text-[13px] text-ink-2">{r.label}</div>
              </foreignObject>
              <line x1={x0} x2={x1} y1={cy} y2={cy} stroke="var(--border)" />
              {hasBand && <rect data-testid="band" x={x(bandLo)} y={cy - 7} width={Math.max(2, x(bandHi) - x(bandLo))} height={14} rx={3} fill="var(--band-strong)" />}
              {num(r.league) && <line x1={x(r.league)} x2={x(r.league)} y1={cy - 8} y2={cy + 8} stroke="var(--text-muted)" strokeWidth={2} />}
              {num(r.season) && <circle cx={x(r.season)} cy={cy} r={5} fill="var(--surface-1)" stroke="var(--text-secondary)" strokeWidth={2} />}
              {num(r.game) && <circle cx={x(r.game)} cy={cy} r={5.5} fill={color} stroke="var(--surface-1)" strokeWidth={1.5} />}
              {!hasBand && <text x={x0 + 2} y={cy + 20} fontSize={10} className="fill-[var(--text-muted)]">no league range</text>}
              <text x={width - 2} y={cy - 2} textAnchor="end" fontWeight={600} className="tabular fill-[var(--text-primary)]">{num(r.game) ? format(r.game) : '–'}</text>
              {d != null && (
                <text x={width - 2} y={cy + 12} textAnchor="end" fontSize={11} className="tabular fill-[var(--text-muted)]">{delta(d)} vs season</text>
              )}
            </g>
          )
        })}
      </svg>
      {card(rows.find((r) => r.key === at?.key)?.tip)}
      </div>
    </div>
  )
}

function plain(label: ReactNode): string {
  return typeof label === 'string' || typeof label === 'number' ? String(label) : 'metric'
}
