/**
 * Horizontal bars around zero, one per row: "how much did each group push toward each team".
 * Positive values go right (toward `rightLabel`). Labels sit on the row; values at the bar end.
 * A row's `overlay` draws a second value as an outlined bar on the same row, for comparing one
 * reading with another without leaving the chart. The outline is one neutral ink whichever approach
 * it is: color on these bars means a team.
 */
import { scaleLinear } from 'd3-scale'
import type { CSSProperties, ReactNode } from 'react'
import { useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type DivRow = { key: string; label: ReactNode; value: number | null; overlay?: number | null; color?: string; title?: string; tip?: ReactNode }

export function DivergingBars({ rows, leftLabel, rightLabel, format, rowHeight = 26, labelWidth = 150, domain, leftColor = 'var(--div-neg)', rightColor = 'var(--div-pos)', overlayName, ariaLabel }: {
  rows: DivRow[]
  leftLabel?: string
  rightLabel?: string
  format: (v: number) => string
  rowHeight?: number
  labelWidth?: number
  domain?: number
  leftColor?: string
  rightColor?: string
  /** Named next to an overlay's value where there's room, so the two numbers can't be mistaken for each other. */
  overlayName?: string
  ariaLabel?: string
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const lw = width < 480 ? Math.min(110, labelWidth) : labelWidth
  const valW = 64
  const max = domain ?? Math.max(1e-9, ...rows.map((r) => Math.abs(r.value ?? 0)))
  const x = scaleLinear().domain([-max, max]).range([lw + valW, width - valW]).clamp(true)
  const head = leftLabel || rightLabel ? 20 : 0
  const h = head + rows.length * rowHeight + 4
  const hovered = rows.find((r) => r.key === at?.key)
  const barH = Math.min(rowHeight - 10, 20)
  const barY = (rowHeight - barH) / 2
  const overlayText = (o: number) => `${width >= 640 && overlayName ? `${overlayName} ` : ''}${format(o)}`
  /** A value's label, sitting past its bar on its own side. */
  const label = (v: number, y: number, parts: ReactNode) => (
    <text x={v >= 0 ? x(v) + 6 : x(v) - 6} y={y + rowHeight / 2 + 4} textAnchor={v >= 0 ? 'start' : 'end'} className="tabular fill-[var(--text-secondary)]">{parts}</text>
  )
  const quiet = (t: string) => <tspan className="fill-[var(--text-muted)]">{t}</tspan>
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={h} role="img" aria-label={ariaLabel} className="block overflow-visible text-[12px]">
          {head > 0 && (
            <g className="fill-[var(--text-muted)]">
              <text x={x(0) - 6} y={12} textAnchor="end">← {leftLabel}</text>
              <text x={x(0) + 6} y={12}>{rightLabel} →</text>
            </g>
          )}
          <line x1={x(0)} x2={x(0)} y1={head} y2={h} stroke="var(--border)" />
          {rows.map((r, i) => {
            const y = head + i * rowHeight
            const v = r.value ?? 0
            const x0 = Math.min(x(0), x(v))
            const w = Math.abs(x(v) - x(0))
            const fill = r.color ?? (v >= 0 ? rightColor : leftColor)
            const o = r.overlay
            const together = o != null && r.value != null && (v === 0 || o === 0 || Math.sign(o) === Math.sign(v))
            const on = hovered?.key === r.key
            // grows from the axis: a bar going left is anchored at its right end
            const grow = (v2: number) => ({ className: 'bar-grow', style: { '--i': Math.min(i, 7), transformOrigin: v2 >= 0 ? 'left' : 'right' } as CSSProperties })
            return (
              <g key={r.key} {...(r.tip ? bind(r.key) : {})}>
                {r.title && !r.tip && <title>{r.title}</title>}
                {r.tip && <rect x={0} y={y} width={width} height={rowHeight} rx={4} fill={on ? 'var(--surface-2)' : 'transparent'} />}
                <foreignObject x={0} y={y} width={lw - 8} height={rowHeight}>
                  <div className="flex h-full items-center truncate text-[13px] text-ink-2">{r.label}</div>
                </foreignObject>
                {r.value != null && <rect x={x0} y={y + barY} width={Math.max(1, w)} height={barH} rx={3} fill={fill} {...grow(v)} />}
                {o != null && (
                  <rect data-testid="overlay" x={Math.min(x(0), x(o))} y={y + barY - 4} width={Math.max(1, Math.abs(x(o) - x(0)))} height={barH + 8} rx={3} fill="none" stroke="var(--text-primary)" strokeWidth={1.5} {...grow(o)} />
                )}
                {r.value == null && o == null && <text x={x(0) + 6} y={y + rowHeight / 2 + 4} className="fill-[var(--text-muted)]">no data</text>}
                {r.value != null && !together && label(v, y, format(v))}
                {o != null && !together && label(o, y, quiet(overlayText(o)))}
                {together && label(Math.abs(o) > Math.abs(v) ? o : v, y, <>{format(v)}{quiet(` · ${overlayText(o)}`)}</>)}
              </g>
            )
          })}
        </svg>
        {card(hovered?.tip)}
      </div>
    </div>
  )
}
