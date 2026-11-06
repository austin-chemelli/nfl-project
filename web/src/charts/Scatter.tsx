/**
 * Scatter of labelled points on two axes, hand-rolled on d3-scale. Square at phone width, about
 * 16:10 on wider screens. Dashed lines mark the league means; quadrant captions sit in the corners
 * and are obstacles for the labels. Labels come from `placeLabels` (a crowded dot may go without
 * one; hover and focus name it). The selected and hovered points get a ring and a label, drawn in
 * a top layer so the focus order of the 32 stops never changes.
 */
import { scaleLinear } from 'd3-scale'
import type { KeyboardEvent, ReactNode } from 'react'
import { useChartTip } from './ChartTip'
import { placeLabels, type Rect } from './labels'
import { useWidth } from './useWidth'

export type ScatterTone = 'conf-afc' | 'conf-nfc' | 'muted' | 'strong'

export type ScatterPoint = { key: string; label: string; x: number; y: number; tone?: ScatterTone }

export type ScatterAxis = {
  title: string
  /** Draw the lowest value at the right or top, so "better" points the same way on both axes. */
  flip?: boolean
  /** League mean: a dashed line. */
  mean?: number
  format: (v: number) => string
  /** Add "better →" or "↑ better" to the title. Only for a measure with a direction. */
  better?: boolean
}

export type ScatterProps = {
  points: ScatterPoint[]
  x: ScatterAxis
  y: ScatterAxis
  /** Corner captions: top left, top right, bottom left, bottom right. */
  quadrants?: [string, string, string, string]
  selected?: string | null
  onSelect?: (key: string) => void
  tip?: (key: string) => ReactNode
  /** Names the chart for assistive tech; the per-point list is added to it. */
  label: string
}

const R = 5
const HIT = 14
const M = { l: 60, r: 24, t: 26, b: 46 }
const CAP_FS = 10
const CAP_CH = 5.4

const fillOf = (t?: ScatterTone) =>
  t === 'conf-afc' ? 'var(--conf-afc)' : t === 'conf-nfc' ? 'var(--conf-nfc)' : t === 'strong' ? 'var(--text-primary)' : t === 'muted' ? 'var(--text-muted)' : 'var(--text-secondary)'
const opacityOf = (t?: ScatterTone) => (t === 'muted' ? 0.4 : 0.9)

function wrap(text: string, maxChars: number): string[] {
  const lines: string[] = []
  let cur = ''
  for (const w of text.split(/\s+/)) {
    if (cur && (cur + ' ' + w).length > maxChars) {
      lines.push(cur)
      cur = w
    } else cur = cur ? cur + ' ' + w : w
  }
  if (cur) lines.push(cur)
  return lines.slice(0, 3)
}

function domainOf(vals: number[], mean?: number): [number, number] {
  const all = mean == null || !Number.isFinite(mean) ? vals : [...vals, mean]
  if (!all.length) return [0, 1]
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const pad = (hi - lo) * 0.06 || 1
  return [lo - pad, hi + pad]
}

export function Scatter({ points, x, y, quadrants, selected, onSelect, tip, label }: ScatterProps) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const innerW = Math.max(120, width - M.l - M.r)
  const innerH = width < 480 ? innerW : Math.min(520, Math.round((innerW * 10) / 16))
  const h = innerH + M.t + M.b
  const [xd, yd] = [domainOf(points.map((p) => p.x), x.mean), domainOf(points.map((p) => p.y), y.mean)]
  const sx = scaleLinear().domain(xd).range(x.flip ? [M.l + innerW, M.l] : [M.l, M.l + innerW])
  const sy = scaleLinear().domain(yd).range(y.flip ? [M.t, M.t + innerH] : [M.t + innerH, M.t])
  const px = points.map((p) => ({ ...p, cx: sx(p.x), cy: sy(p.y) }))
  const hovered = at?.key ?? null

  // quadrant captions: wrapped to fit half the plot, and obstacles for the labels
  const half = innerW / 2 - 8
  const maxChars = Math.max(8, Math.floor(half / CAP_CH))
  const caps = (quadrants ?? []).map((text, i) => {
    const lines = wrap(text, maxChars)
    const w = Math.min(half, Math.max(...lines.map((l) => l.length), 0) * CAP_CH + 2)
    const ch = lines.length * (CAP_FS + 2)
    const right = i % 2 === 1
    const bottom = i >= 2
    const rect: Rect = { x: right ? M.l + innerW - 4 - w : M.l + 4, y: bottom ? M.t + innerH - 4 - ch : M.t + 4, w, h: ch }
    return { lines, rect, right }
  })
  const centre = { x: x.mean == null ? undefined : sx(x.mean), y: y.mean == null ? undefined : sy(y.mean) }
  // A highlighted point (tone `strong`) keeps its label, however crowded the plot.
  const forced = [selected, ...points.filter((p) => p.tone === 'strong').map((p) => p.key)].filter((k): k is string => !!k)
  const area = { width: M.l + innerW + M.r, height: M.t + innerH + M.b }
  const toLabel = (p: (typeof px)[number]) => ({ key: p.key, text: p.label, x: p.cx, y: p.cy })
  const base = placeLabels(
    px.map(toLabel),
    area,
    { obstacles: caps.map((c) => c.rect), forced, radius: R, center: centre.x != null && centre.y != null ? { x: centre.x, y: centre.y } : undefined },
  )
  // A hovered point fits around the labels already placed, so its neighbours don't jump as the pointer moves.
  const hoverPoint = hovered && !base.some((l) => l.key === hovered) ? px.find((p) => p.key === hovered) : undefined
  const placed = hoverPoint
    ? [...base, ...placeLabels([toLabel(hoverPoint)], area, { obstacles: [...caps.map((c) => c.rect), ...base], forced: [hoverPoint.key], radius: R })]
    : base
  const byKey = new Map(px.map((p) => [p.key, p]))
  const labelFor = (k: string) => placed.find((l) => l.key === k)
  const normal = placed.filter((l) => l.key !== selected && l.key !== hovered) // those two draw in the top layer

  const aria = `${label}: ${points.map((p) => `${p.label}, ${x.title} ${x.format(p.x)}, ${y.title} ${y.format(p.y)}`).join('; ')}`
  const xTitle = x.title + (x.better ? ' · better →' : '')
  const yTitle = (y.better ? '↑ better · ' : '') + y.title
  const act = (key: string) => ({
    onClick: () => onSelect?.(key),
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onSelect?.(key)
      }
    },
  })
  const hv = hovered ? byKey.get(hovered) : undefined
  const sel = selected ? byKey.get(selected) : undefined
  const top = [sel, hv && hv !== sel ? hv : undefined].filter((p): p is NonNullable<typeof p> => !!p)

  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={h} role="img" aria-label={aria} className="block max-w-full text-[11px]">
          <rect x={M.l} y={M.t} width={innerW} height={innerH} fill="var(--surface-1)" stroke="var(--border)" />
          {sx.ticks(4).map((t) => (
            <g key={`xt${t}`}>
              <line x1={sx(t)} x2={sx(t)} y1={M.t + innerH} y2={M.t + innerH + 4} stroke="var(--border)" />
              <text x={sx(t)} y={M.t + innerH + 16} textAnchor="middle" className="tabular fill-[var(--text-muted)]">{x.format(t)}</text>
            </g>
          ))}
          {sy.ticks(4).map((t) => (
            <g key={`yt${t}`}>
              <line x1={M.l - 4} x2={M.l} y1={sy(t)} y2={sy(t)} stroke="var(--border)" />
              <text x={M.l - 7} y={sy(t) + 4} textAnchor="end" className="tabular fill-[var(--text-muted)]">{y.format(t)}</text>
            </g>
          ))}
          {x.mean != null && <line data-testid="mean-x" x1={sx(x.mean)} x2={sx(x.mean)} y1={M.t} y2={M.t + innerH} stroke="var(--text-muted)" strokeDasharray="4 4" />}
          {y.mean != null && <line data-testid="mean-y" x1={M.l} x2={M.l + innerW} y1={sy(y.mean)} y2={sy(y.mean)} stroke="var(--text-muted)" strokeDasharray="4 4" />}
          {caps.map((c, i) => (
            <text key={i} data-testid="quadrant" textAnchor={c.right ? 'end' : 'start'} fontSize={CAP_FS} className="fill-[var(--text-muted)]">
              {c.lines.map((l, j) => (
                <tspan key={j} x={c.right ? c.rect.x + c.rect.w : c.rect.x} y={c.rect.y + CAP_FS + j * (CAP_FS + 2) - 1}>{l}</tspan>
              ))}
            </text>
          ))}
          <text x={M.l + innerW / 2} y={h - 6} textAnchor="middle" fontSize={12} className="fill-[var(--text-secondary)]">{xTitle}</text>
          {/* above the plot, not rotated: tick labels vary in width and a rotated title collides with long ones */}
          <text x={M.l} y={14} fontSize={12} className="fill-[var(--text-secondary)]">{yTitle}</text>
          {px.map((p) => (
            <g key={p.key} data-testid="point" data-key={p.key} aria-label={`${p.label}: ${x.title} ${x.format(p.x)}, ${y.title} ${y.format(p.y)}`} {...bind(p.key)} {...act(p.key)} className="cursor-pointer">
              <circle cx={p.cx} cy={p.cy} r={HIT} fill="transparent" />
              <circle cx={p.cx} cy={p.cy} r={R} fill={fillOf(p.tone)} fillOpacity={opacityOf(p.tone)} stroke="var(--surface-1)" strokeWidth={1} />
            </g>
          ))}
          <g aria-hidden pointerEvents="none">
            {normal.map((l) => (
              <text key={l.key} data-testid="label" x={l.x + 2} y={l.y + 9.5} fill="var(--text-secondary)" fillOpacity={byKey.get(l.key)?.tone === 'muted' ? 0.6 : 1}>{l.text}</text>
            ))}
            {top.map((p) => {
              const l = labelFor(p.key)
              const isSel = p === sel
              return (
                <g key={p.key} data-testid={isSel ? 'selected' : 'hovered'}>
                  <circle cx={p.cx} cy={p.cy} r={R + (isSel ? 4 : 3)} fill="none" stroke="var(--text-primary)" strokeWidth={isSel ? 2.5 : 1.5} />
                  <circle cx={p.cx} cy={p.cy} r={R} fill={fillOf(p.tone)} stroke="var(--surface-1)" strokeWidth={1} />
                  {l && <text data-testid="label" x={l.x + 2} y={l.y + 9.5} fontWeight={600} fill="var(--text-primary)">{l.text}</text>}
                </g>
              )
            })}
          </g>
        </svg>
        {card(tip && hovered ? tip(hovered) : null)}
      </div>
    </div>
  )
}
