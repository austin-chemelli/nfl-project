/**
 * Horizontal bars around zero, one per row: "how much did each group push toward each team".
 * Positive values go right (toward `rightLabel`). Labels sit on the row; values at the bar end.
 * A row's `overlay` draws a second value as an outlined bar on the same row, for comparing one
 * reading with another without leaving the chart.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useWidth } from './useWidth'

export type DivRow = { key: string; label: ReactNode; value: number | null; overlay?: number | null; color?: string; title?: string }

export function DivergingBars({ rows, leftLabel, rightLabel, format, rowHeight = 26, labelWidth = 150, domain, overlayColor = 'var(--text-secondary)', ariaLabel }: {
  rows: DivRow[]
  leftLabel?: string
  rightLabel?: string
  format: (v: number) => string
  rowHeight?: number
  labelWidth?: number
  domain?: number
  overlayColor?: string
  ariaLabel?: string
}) {
  const [ref, width] = useWidth()
  const lw = width < 480 ? Math.min(110, labelWidth) : labelWidth
  const valW = 64
  const max = domain ?? Math.max(1e-9, ...rows.map((r) => Math.abs(r.value ?? 0)))
  const x = scaleLinear().domain([-max, max]).range([lw + valW, width - valW]).clamp(true)
  const head = leftLabel || rightLabel ? 20 : 0
  const h = head + rows.length * rowHeight + 4
  return (
    <div ref={ref} className="w-full">
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
          const fill = r.color ?? (v >= 0 ? 'var(--div-pos)' : 'var(--div-neg)')
          const o = r.overlay
          // the value sits past whichever bar reaches further on its side
          const reach = o != null && (v === 0 || Math.sign(o) === Math.sign(v)) && Math.abs(o) > Math.abs(v) ? o : v
          return (
            <g key={r.key}>
              <title>{r.title ?? ''}</title>
              <foreignObject x={0} y={y} width={lw - 8} height={rowHeight}>
                <div className="flex h-full items-center truncate text-[13px] text-ink-2">{r.label}</div>
              </foreignObject>
              {o != null && (
                <rect data-testid="overlay" x={Math.min(x(0), x(o))} y={y + 2} width={Math.max(1, Math.abs(x(o) - x(0)))} height={rowHeight - 4} rx={2} fill="none" stroke={overlayColor} strokeWidth={1.5} />
              )}
              {r.value == null ? (
                o == null ? (
                  <text x={x(0) + 6} y={y + rowHeight / 2 + 4} className="fill-[var(--text-muted)]">no data</text>
                ) : (
                  <text x={o >= 0 ? x(o) + 6 : x(o) - 6} y={y + rowHeight / 2 + 4} textAnchor={o >= 0 ? 'start' : 'end'} className="tabular" fill={overlayColor}>{format(o)}</text>
                )
              ) : (
                <>
                  <rect x={x0} y={y + 5} width={Math.max(1, w)} height={rowHeight - 10} rx={2} fill={fill} />
                  <text
                    x={reach >= 0 ? x(reach) + 6 : x(reach) - 6}
                    y={y + rowHeight / 2 + 4}
                    textAnchor={reach >= 0 ? 'start' : 'end'}
                    className="tabular fill-[var(--text-secondary)]"
                  >
                    {format(v)}
                    {o != null && <tspan fill={overlayColor}> · {format(o)}</tspan>}
                  </text>
                </>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
