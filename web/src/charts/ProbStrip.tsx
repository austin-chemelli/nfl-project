/**
 * Home win probability on a 0-100% strip: the market as a vertical line, one dot per model (approach colors;
 * references hollow). Compact is one 20px row for slate cards; expanded has ticks, labels and a label column.
 * Expanded dots slide in from the market line (compact ones, up to 15 a page, stay still) and show a tip card
 * on hover, focus and tap; compact keeps `<title>` since the strip sits inside a link.
 */
import { scaleLinear } from 'd3-scale'
import type { CSSProperties } from 'react'
import { colorVar } from '../lib/models'
import { pct } from '../lib/format'
import { TipRow, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type ProbModel = { id: string; label: string; p: number; reference?: boolean }
const TICKS = [0, 0.25, 0.5, 0.75, 1]

export function ProbStrip({ models, market, home, compact = false }: {
  models: ProbModel[]
  market: number | null
  home: string
  compact?: boolean
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const lw = compact ? 0 : width < 480 ? 104 : 128
  const x0 = lw + 8
  const x1 = width - 8
  const x = scaleLinear().domain([0, 1]).range([x0, x1])
  const r = compact ? 4 : 6
  const rowH = compact ? 20 : 28
  const axisH = compact ? 0 : 20
  const rows = compact ? 1 : Math.max(1, models.length)
  const h = rows * rowH + axisH
  const aria = `Home win chance for ${home}: ${market != null ? `market ${pct(market)}${models.length ? ', ' : ''}` : ''}${models.map((m) => `${m.label} ${pct(m.p)}`).join(', ')}`

  const tipped = models.find((m) => m.id === at?.key)

  const dot = (m: ProbModel, cy: number) => (
    <circle
      key={m.id}
      data-testid="dot"
      cx={x(m.p)}
      cy={cy}
      r={r}
      fill={m.reference ? 'var(--surface-1)' : colorVar(m.id)}
      stroke={m.reference ? 'var(--series-ref)' : 'var(--surface-1)'}
      strokeWidth={m.reference ? 2 : 1.5}
      className={!compact && market != null ? 'dot-slide' : undefined}
      style={!compact && market != null ? ({ '--from-x': `${x(market) - x(m.p)}px` } as CSSProperties) : undefined}
    >
      {compact && <title>{`${m.label}: ${home} ${pct(m.p, 1)}`}</title>}
    </circle>
  )

  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
      <svg width={width} height={h} role="img" aria-label={aria} className="block text-[12px]">
        {compact ? (
          <>
            <line x1={x0} x2={x1} y1={rowH / 2} y2={rowH / 2} stroke="var(--border)" />
            <line x1={x(0.5)} x2={x(0.5)} y1={rowH / 2 - 4} y2={rowH / 2 + 4} stroke="var(--border)" />
            {market != null && <line data-testid="market" x1={x(market)} x2={x(market)} y1={1} y2={rowH - 1} stroke="var(--series-market)" strokeWidth={2} opacity={0.6} />}
            {models.map((m) => dot(m, rowH / 2))}
          </>
        ) : (
          <>
            {models.map((m, i) => {
              const cy = i * rowH + rowH / 2
              return (
                <g key={m.id} {...bind(m.id)}>
                  <rect x={0} y={i * rowH} width={width} height={rowH} rx={4} fill={at?.key === m.id ? 'var(--surface-2)' : 'transparent'} />
                  <foreignObject x={0} y={i * rowH} width={lw} height={rowH}>
                    <div className="flex h-full items-center gap-1.5 truncate text-[13px] text-ink-2">
                      <span aria-hidden className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: m.reference ? 'var(--surface-1)' : colorVar(m.id), border: m.reference ? '2px solid var(--series-ref)' : undefined }} />
                      {m.label}
                    </div>
                  </foreignObject>
                  <line x1={x0} x2={x1} y1={cy} y2={cy} stroke="var(--border)" />
                  {TICKS.map((t) => <line key={t} x1={x(t)} x2={x(t)} y1={cy - 4} y2={cy + 4} stroke="var(--border)" />)}
                  {dot(m, cy)}
                </g>
              )
            })}
            {market != null && <line data-testid="market" x1={x(market)} x2={x(market)} y1={2} y2={rows * rowH - 2} stroke="var(--series-market)" strokeWidth={2} opacity={0.6} />}
            {TICKS.map((t) => (
              <text key={t} x={x(t)} y={rows * rowH + 14} textAnchor="middle" className="fill-[var(--text-muted)]" fontSize={11}>{Math.round(t * 100)}%</text>
            ))}
          </>
        )}
      </svg>
      {!compact && card(tipped && <TipRow color={tipped.reference ? 'var(--series-ref)' : colorVar(tipped.id)} value={pct(tipped.p, 1)} label={`${tipped.label}: ${home}`} />)}
      </div>
      {!compact && <div className="text-center text-[12px] text-ink-3">{home} win probability{market != null ? ' · gray line is the market' : ''}</div>}
    </div>
  )
}
