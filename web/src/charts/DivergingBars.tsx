/**
 * Horizontal bars around zero, one per row: "how much did each group push toward each team".
 * Positive values go right (toward `rightLabel`). Labels sit on the row; values at the bar end.
 */
import { scaleLinear } from 'd3-scale'
import type { ReactNode } from 'react'
import { useWidth } from './useWidth'

export type DivRow = { key: string; label: ReactNode; value: number | null; color?: string; title?: string }

export function DivergingBars({ rows, leftLabel, rightLabel, format, rowHeight = 26, labelWidth = 150, domain }: {
  rows: DivRow[]
  leftLabel?: string
  rightLabel?: string
  format: (v: number) => string
  rowHeight?: number
  labelWidth?: number
  domain?: number
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
      <svg width={width} height={h} role="img" className="block overflow-visible text-[12px]">
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
          return (
            <g key={r.key}>
              <title>{r.title ?? ''}</title>
              <foreignObject x={0} y={y} width={lw - 8} height={rowHeight}>
                <div className="flex h-full items-center truncate text-[13px] text-ink-2">{r.label}</div>
              </foreignObject>
              {r.value == null ? (
                <text x={x(0) + 6} y={y + rowHeight / 2 + 4} className="fill-[var(--text-muted)]">no data</text>
              ) : (
                <>
                  <rect x={x0} y={y + 5} width={Math.max(1, w)} height={rowHeight - 10} rx={2} fill={fill} />
                  <text
                    x={v >= 0 ? x(v) + 6 : x(v) - 6}
                    y={y + rowHeight / 2 + 4}
                    textAnchor={v >= 0 ? 'start' : 'end'}
                    className="tabular fill-[var(--text-secondary)]"
                  >
                    {format(v)}
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
