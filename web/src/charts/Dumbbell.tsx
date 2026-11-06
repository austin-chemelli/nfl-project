/**
 * Two teams' values on one metric, with the league average as a tick: tendencies vs league.
 * `a` and `b` are the two teams (away, home); null values are drawn as "no data".
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type DumbbellRow = { key: string; label: ReactNode; a: number | null; b: number | null; league: number | null; title?: string; bColor?: string; help?: string }

export function Dumbbell({ rows, aName, bName, aColor = 'var(--series-traditionalist)', bColor = 'var(--series-analyst)', format, domain, rowHeight = 28, labelWidth = 170, legend, decorative }: {
  rows: DumbbellRow[]
  aName: string
  bName: string
  aColor?: string
  bColor?: string
  format: (v: number) => string
  domain?: [number, number]
  rowHeight?: number
  labelWidth?: number
  /** Replaces the default legend (when rows color their `b` dot themselves). */
  legend?: ReactNode
  /** Hides the svg from assistive tech, where the values are printed beside it. */
  decorative?: boolean
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const lw = width < 480 ? Math.min(110, labelWidth) : labelWidth
  const vals = rows.flatMap((r) => [r.a, r.b, r.league]).filter((v): v is number => v != null)
  const [d0, d1] = domain ?? [Math.min(...vals, 0), Math.max(...vals, 0.01)]
  const x = scaleLinear().domain([d0, d1]).range([lw + 8, width - 48]).nice()
  const head = 22
  const h = head + rows.length * rowHeight + 4
  const hovered = rows.find((r) => r.key === at?.key)
  return (
    <div ref={ref} className="w-full">
      {legend ?? (
        <div className="mb-1 flex gap-4 text-[12px] text-ink-2">
          <span className="inline-flex items-center gap-1"><Dot c={aColor} /> {aName}</span>
          <span className="inline-flex items-center gap-1"><Dot c={bColor} /> {bName}</span>
          <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-0.5 bg-[var(--text-muted)]" /> League average</span>
        </div>
      )}
      <div ref={box} className="relative">
      <svg width={width} height={h} {...(decorative ? { 'aria-hidden': true } : { role: 'img' })} className="block text-[12px]">
        {rows.map((r, i) => {
          const y = head + i * rowHeight + rowHeight / 2 - 10
          const pts = [r.a, r.b].filter((v): v is number => v != null)
          return (
            <g key={r.key} {...bind(r.key)}>
              <rect x={0} y={y - rowHeight / 2} width={width} height={rowHeight} rx={4} fill={hovered?.key === r.key ? 'var(--surface-2)' : 'transparent'} />
              <foreignObject x={0} y={y - rowHeight / 2} width={lw} height={rowHeight}>
                <div className="flex h-full items-center truncate text-[13px] text-ink-2">{r.label}</div>
              </foreignObject>
              <line x1={lw + 8} x2={width - 48} y1={y} y2={y} stroke="var(--border)" />
              {pts.length === 2 && <line x1={x(pts[0])} x2={x(pts[1])} y1={y} y2={y} stroke="var(--text-muted)" strokeWidth={2} />}
              {r.league != null && <line x1={x(r.league)} x2={x(r.league)} y1={y - 7} y2={y + 7} stroke="var(--text-muted)" strokeWidth={2} />}
              {r.a != null && <circle cx={x(r.a)} cy={y} r={5} fill={aColor} stroke="var(--surface-1)" strokeWidth={1.5} />}
              {r.b != null && <circle cx={x(r.b)} cy={y} r={5} fill={r.bColor ?? bColor} stroke="var(--surface-1)" strokeWidth={1.5} />}
              {pts.length === 0 && <text x={lw + 12} y={y + 4} className="fill-[var(--text-muted)]">no data</text>}
            </g>
          )
        })}
      </svg>
      {card(
        hovered && (
          <>
            <TipTitle note={hovered.help}>{hovered.label}</TipTitle>
            <TipRow color={aColor} value={hovered.a == null ? '–' : format(hovered.a)} label={aName} />
            <TipRow color={hovered.bColor ?? bColor} value={hovered.b == null ? '–' : format(hovered.b)} label={bName} />
            {hovered.league != null && <TipNote>League average {format(hovered.league)}</TipNote>}
          </>
        ),
      )}
      </div>
    </div>
  )
}

function Dot({ c }: { c: string }) {
  return <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />
}
