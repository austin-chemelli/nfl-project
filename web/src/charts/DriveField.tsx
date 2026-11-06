/**
 * Every drive on one field (ADR 0020): a row per drive in time order, a bar from where it started to
 * where it ended in the offense's color, and a glyph for how it ended. The away team drives left to
 * right and the home team right to left, so the end zones can carry the team colors. No logos (ADR 0011).
 */
import { scaleLinear } from 'd3-scale'
import type { CSSProperties } from 'react'
import type { Drive } from '../data/contract'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
import type { DriveTip } from './PossessionStrip'
import { useWidth } from './useWidth'

type Glyph = 'score' | 'kick' | 'miss' | 'punt' | 'lost' | null

const GLYPHS: Record<string, Glyph> = {
  Touchdown: 'score',
  'Field goal': 'kick',
  'Missed field goal': 'miss',
  Punt: 'punt',
  Turnover: 'lost',
  'Turnover on downs': 'lost',
  'Opp touchdown': 'lost',
  Safety: 'lost',
}

// oxlint-disable-next-line react/only-export-components
export const driveGlyph = (result: string | null): Glyph => (result ? (GLYPHS[result] ?? null) : null)

function Mark({ glyph, x, y, color }: { glyph: Glyph; x: number; y: number; color: string }) {
  if (!glyph) return null
  const r = 4
  const stroke = { stroke: color, strokeWidth: 2, strokeLinecap: 'round' as const }
  return (
    <g data-glyph={glyph}>
      {glyph === 'score' && <circle cx={x} cy={y} r={r + 0.5} fill={color} stroke="var(--surface-1)" strokeWidth={1} />}
      {glyph === 'kick' && <circle cx={x} cy={y} r={r} fill="var(--surface-1)" {...stroke} />}
      {glyph === 'miss' && <circle cx={x} cy={y} r={r} fill="var(--surface-1)" {...stroke} strokeDasharray="2 2.5" strokeLinecap="butt" />}
      {glyph === 'punt' && <line x1={x} x2={x} y1={y - r} y2={y + r} {...stroke} />}
      {glyph === 'lost' && (
        <>
          <line x1={x - r} x2={x + r} y1={y - r} y2={y + r} {...stroke} />
          <line x1={x - r} x2={x + r} y1={y + r} y2={y - r} {...stroke} />
        </>
      )}
    </g>
  )
}

const LEGEND: [Glyph, string][] = [['score', 'Touchdown'], ['kick', 'Field goal'], ['miss', 'Missed kick'], ['punt', 'Punt'], ['lost', 'Lost the ball']]

const HEAD = 20
const FOOT = 18
const qtrLabel = (q: number) => (q >= 5 ? 'OT' : `Q${q}`)

export function DriveField({ drives, home, away, describe }: {
  drives: Drive[]
  home: string
  away: string
  describe: (d: Drive) => DriveTip
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const narrow = width < 480
  const rowH = narrow ? 15 : 18
  const left = narrow ? 58 : 72
  const h = HEAD + drives.length * rowH + FOOT
  const bottom = h - FOOT
  const x = scaleLinear().domain([-10, 110]).range([left, width - 4])
  const color = (d: Drive) => `var(--team-${d.team === home ? 'home' : 'away'})`
  // yards from the offense's own goal, placed on a field with the away team's goal on the left
  const pos = (d: Drive, yl: number) => x(d.team === home ? 100 - yl : yl)
  const yards = narrow ? [20, 50, 80] : [10, 20, 30, 40, 50, 60, 70, 80, 90]
  const active = drives.find((d) => String(d.n) === at?.key)
  const tip = active ? describe(active) : null
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={h} className="block text-[11px]">
          <rect x={x(-10)} y={0} width={x(0) - x(-10)} height={bottom} fill="var(--team-away)" fillOpacity={0.22} />
          <rect x={x(100)} y={0} width={x(110) - x(100)} height={bottom} fill="var(--team-home)" fillOpacity={0.22} />
          <text x={x(-5)} y={13} textAnchor="middle" fontWeight={600} fontSize={narrow ? 9.5 : 11} className="fill-[var(--text-secondary)]">{away}</text>
          <text x={x(105)} y={13} textAnchor="middle" fontWeight={600} fontSize={narrow ? 9.5 : 11} className="fill-[var(--text-secondary)]">{home}</text>
          {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map((v) => (
            <line key={v} x1={x(v)} x2={x(v)} y1={0} y2={bottom} stroke={v === 50 ? 'var(--text-muted)' : 'var(--border)'} />
          ))}
          {yards.map((v) => (
            <text key={v} x={x(v)} y={h - 5} textAnchor="middle" className="tabular fill-[var(--text-muted)]">{v > 50 ? 100 - v : v}</text>
          ))}
          {active && <rect x={0} y={HEAD + drives.indexOf(active) * rowH} width={width} height={rowH} rx={3} fill="var(--surface-2)" />}
          {drives.map((d, i) => {
            const y = HEAD + i * rowH + rowH / 2
            const newQtr = i === 0 || drives[i - 1].qtr !== d.qtr
            // a touchdown's last snap is short of the line the ball crossed
            const end = d.result === 'Touchdown' ? 100 : d.end_yl
            const drawn = d.start_yl != null && end != null
            const x0 = d.start_yl != null ? pos(d, d.start_yl) : null
            const x1 = end != null ? pos(d, end) : null
            const tipFor = describe(d)
            return (
              <g key={d.n} {...bind(String(d.n))} role="group" data-testid="drive-row" aria-label={[tipFor.title, tipFor.result, tipFor.span, tipFor.detail].filter(Boolean).join(', ')}>
                <rect x={0} y={y - rowH / 2} width={width} height={rowH} fill="transparent" />
                {newQtr && i > 0 && <line x1={0} x2={width} y1={y - rowH / 2} y2={y - rowH / 2} stroke="var(--border)" />}
                {newQtr && <text x={0} y={y + 4} className="fill-[var(--text-muted)]">{qtrLabel(d.qtr)}</text>}
                <text x={left - 6} y={y + 4} textAnchor="end" className="fill-[var(--text-secondary)]">{d.team}</text>
                {drawn && x0 != null && x1 != null && (
                  <rect data-testid="drive-bar" className="bar-grow" x={Math.min(x0, x1)} y={y - 3} width={Math.max(2, Math.abs(x1 - x0))} height={6} rx={2} fill={color(d)} style={{ '--i': Math.min(i, 7), transformOrigin: x1 >= x0 ? 'left' : 'right' } as CSSProperties} />
                )}
                {x1 != null && <Mark glyph={driveGlyph(d.result)} x={x1} y={y} color={color(d)} />}
              </g>
            )
          })}
        </svg>
        {card(tip && (
          <>
            <TipTitle>{tip.title}</TipTitle>
            <TipRow color={active ? color(active) : undefined} value={tip.result} label={tip.span ?? ''} />
            {tip.detail && <TipNote>{tip.detail}</TipNote>}
          </>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-3">
        {LEGEND.map(([g, label]) => (
          <span key={label} className="inline-flex items-center gap-1">
            <svg width={12} height={12} aria-hidden="true"><Mark glyph={g} x={6} y={6} color="var(--text-secondary)" /></svg>
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
