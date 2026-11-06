/**
 * The game's win probability over time (ADR 0020): home win probability on y, elapsed seconds on x with
 * quarter rules, the area between the curve and 50% in each team's color, and the turning points as
 * numbered marks in time order. Marks are a sibling of the `role="img"` group so they stay focusable.
 * The line carries `wp-line` and `pathLength=1` for the draw-in animation in index.css.
 */
import { scaleLinear } from 'd3-scale'
import { useId, type ReactNode } from 'react'
import type { WpPlay, WpSeries } from '../data/contract'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'

export type WpMark = { title: string; helped: 'home' | 'away'; team: string; prob: string; swing: string; text: string; counted: string | null }

const M = { l: 8, r: 10, t: 8, b: 22 }
const QUARTER = 900
const pc = (p: number) => `${Math.round(100 * p)}%`
const period = (t: number) => (t >= 3600 ? 'overtime' : `Q${Math.floor(t / QUARTER) + 1}`)
const teamColor = (side: 'home' | 'away') => `var(--team-${side})`

/** The curve can run through an annotation; a surface-colored outline keeps the words readable. */
const HALO = { stroke: 'var(--surface-1)', strokeWidth: 3, strokeLinejoin: 'round', style: { paintOrder: 'stroke' } } as const

export function WpChart({ series, home, away, homeScore, awayScore, describe }: {
  series: WpSeries
  home: string
  away: string
  homeScore: number
  awayScore: number
  /** Turns a play into the tip's strings (see `markText`). */
  describe: (p: WpPlay) => WpMark
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')
  const { points, end_t: endT, ot } = series
  const height = width < 480 ? 180 : 220
  const x = scaleLinear().domain([0, Math.max(1, endT)]).range([M.l, width - M.r])
  const y = scaleLinear().domain([1, 0]).range([M.t, height - M.b])
  const y50 = y(0.5)
  const plays = [...series.plays].sort((a, b) => a.t - b.t)

  const line = points.map(([t, p], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(p).toFixed(1)}`).join('')
  const first = points[0]
  const last = points[points.length - 1]
  const area = first && last ? `${line}L${x(last[0]).toFixed(1)},${y50}L${x(first[0]).toFixed(1)},${y50}Z` : ''

  const rules = [QUARTER, 2 * QUARTER, 3 * QUARTER, 4 * QUARTER].filter((t) => t < endT)
  const spans: { label: string; mid: number }[] = []
  for (let k = 0; k < 4 && k * QUARTER < endT; k++) spans.push({ label: `Q${k + 1}`, mid: (k * QUARTER + Math.min((k + 1) * QUARTER, endT)) / 2 })
  if (ot && endT > 4 * QUARTER) spans.push({ label: 'OT', mid: (4 * QUARTER + endT) / 2 })

  const margin = homeScore - awayScore
  const winner = margin > 0 ? home : away
  const hi = Math.max(homeScore, awayScore)
  const lo = Math.min(homeScore, awayScore)
  const finalText = `${margin === 0 ? 'Tied' : `${winner} won`} ${hi}–${lo}${ot ? ' (OT)' : ''}`
  const p0 = first?.[1] ?? 0.5
  const kickoff = `${p0 >= 0.5 ? home : away} ${pc(Math.max(p0, 1 - p0))} at kickoff`
  const wl = series.winner_low
  const winnerLow = wl && wl[1] < 0.25 ? wl : null
  const lowSpot = winnerLow ? { cx: x(winnerLow[0]), cy: y(margin > 0 ? winnerLow[1] : 1 - winnerLow[1]) } : null

  const lowText = wl ? `${winner} low of ${pc(wl[1])} in ${period(wl[0])}` : `home low of ${pc(Math.min(...points.map(([, p]) => p)))}`
  const aria = `Win probability: ${kickoff}; ${lowText}; ${finalText}`

  const active = plays.find((p) => String(p.play_id) === at?.key)
  const tip = active ? describe(active) : null

  const clampY = (v: number) => Math.max(M.t + 12, Math.min(height - M.b - 6, v))
  // the note sits on the 50% side of its dot, clear of the team label at the 100% end
  const startPos = first ? { x: x(first[0]) + 10, y: clampY(p0 >= 0.5 ? y(p0) + 17 : y(p0) - 9) } : null
  const endPos = last ? { x: x(last[0]) - 10, y: clampY(last[1] >= 0.5 ? y(last[1]) + 17 : y(last[1]) - 9) } : null

  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={height} className="block text-[11px]" overflow="hidden">
          <g role="img" aria-label={aria}>
            <defs>
              <clipPath id={`${uid}a`}><rect x={M.l} y={M.t} width={width - M.l - M.r} height={y50 - M.t} /></clipPath>
              <clipPath id={`${uid}b`}><rect x={M.l} y={y50} width={width - M.l - M.r} height={height - M.b - y50} /></clipPath>
            </defs>
            {rules.map((t) => (
              <line key={t} data-testid="wp-rule" x1={x(t)} x2={x(t)} y1={M.t} y2={height - M.b} stroke={t === 2 * QUARTER ? 'var(--text-muted)' : 'var(--border)'} strokeWidth={t === 2 * QUARTER ? 1.5 : 1} />
            ))}
            {spans.map((s) => (
              <text key={s.label} x={x(s.mid)} y={height - 6} textAnchor="middle" className="fill-[var(--text-muted)]">{s.label}</text>
            ))}
            <line x1={M.l} x2={width - M.r} y1={y50} y2={y50} stroke="var(--border)" strokeDasharray="4 4" />
            <path d={area} fill="var(--team-home)" fillOpacity={0.18} clipPath={`url(#${uid}a)`} />
            <path d={area} fill="var(--team-away)" fillOpacity={0.18} clipPath={`url(#${uid}b)`} />
            <text x={M.l + 4} y={M.t + 11} className="fill-[var(--text-muted)]" fontWeight={600}>{home} 100%</text>
            <text x={M.l + 4} y={height - M.b - 5} className="fill-[var(--text-muted)]" fontWeight={600}>{away} 100%</text>
            <path d={line} className="wp-line" pathLength={1} fill="none" stroke="var(--text-secondary)" strokeWidth={2} strokeLinejoin="round" />
            {first && <circle data-testid="wp-start" cx={x(first[0])} cy={y(p0)} r={4} fill="var(--text-secondary)" stroke="var(--surface-1)" strokeWidth={1.5} />}
            {last && <circle data-testid="wp-end" cx={x(last[0])} cy={y(last[1])} r={4} fill="var(--text-secondary)" stroke="var(--surface-1)" strokeWidth={1.5} />}
            {lowSpot && <circle data-testid="wp-low" cx={lowSpot.cx} cy={lowSpot.cy} r={6} fill="none" stroke="var(--text-secondary)" strokeWidth={2} />}
            {startPos && <text data-testid="wp-start-note" x={startPos.x} y={startPos.y} {...HALO} className="fill-[var(--text-secondary)]">{kickoff}</text>}
            {endPos && <text data-testid="wp-end-note" x={endPos.x} y={endPos.y} textAnchor="end" {...HALO} className="fill-[var(--text-muted)]">{finalText}</text>}
          </g>
          <g>
            {plays.map((p, i) => {
              const key = String(p.play_id)
              const cx = x(p.t)
              const cy = y(p.p_after)
              const on = at?.key === key
              return (
                <g key={key} {...bind(key)} className="wp-mark" data-testid="wp-mark">
                  <circle cx={cx} cy={cy} r={14} fill="transparent" />
                  <circle cx={cx} cy={cy} r={7} fill={teamColor(p.wpa > 0 ? 'home' : 'away')} stroke={on ? 'var(--text-primary)' : 'var(--surface-1)'} strokeWidth={on ? 2.5 : 1.5} />
                  <text x={cx} y={cy + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} fill="#fff" stroke="rgba(0,0,0,0.6)" strokeWidth={2} paintOrder="stroke" pointerEvents="none">{i + 1}</text>
                </g>
              )
            })}
          </g>
        </svg>
        {card(tip && <MarkTip m={tip} />)}
      </div>
    </div>
  )
}

function MarkTip({ m }: { m: WpMark }): ReactNode {
  return (
    <>
      <TipTitle>{m.title}</TipTitle>
      <TipRow color={teamColor(m.helped)} value={m.prob} label={`${m.team} win probability`} />
      <TipRow color={teamColor(m.helped)} value={m.swing} label={`swing for ${m.team}`} />
      <TipNote>
        <div>{m.text}</div>
        {m.counted && <div className="mt-1 text-ink-2">{m.counted}</div>}
      </TipNote>
    </>
  )
}
