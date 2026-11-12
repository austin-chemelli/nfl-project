/**
 * One team's starters on a field diagram (ADR 0027, M24.5): the base offense and base defense from the
 * latest depth chart, line of scrimmage at the top. A dot's ring is sized by what the player is worth
 * in points; the filled core is the share of that value expected to play (all of it when he isn't on
 * the report, none when he's Out), so the empty part is the value at risk. Groups the model doesn't
 * value yet (linebackers, interior linemen) are dashed rings with no number. Listed players carry a
 * status letter. The team color comes from `[data-matchup]` (`matchupVars`), never a raw brand color.
 */
import type { LineupSpot, SideLineup } from '../data/contract'
import { kickoffEt } from '../lib/format'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'

const W = 320
const H = 136
const LOS = 18

// Spot -> (x, y) on a 320 x 136 field, offense and defense each facing the line at the top.
const SPOTS: Record<string, [number, number]> = {
  LT: [100, 34], LG: [130, 34], C: [160, 34], RG: [190, 34], RT: [220, 34], TE: [252, 34],
  WR1: [22, 34], WR2: [298, 34], WR3: [62, 52], QB: [160, 72], RB: [160, 110],
  LDE: [100, 34], LDT: [138, 34], NT: [160, 34], RDT: [182, 34], RDE: [220, 34],
  WLB: [76, 62], LILB: [136, 72], MLB: [160, 72], RILB: [184, 72], SLB: [244, 62],
  LCB: [22, 40], RCB: [298, 40], SS: [124, 112], FS: [196, 112],
}

const MAX_PTS = 6.5 // about the best quarterback's value: the largest ring
const R_MIN = 3.5
const R_SPAN = 12.5
const ringR = (pts: number) => R_MIN + R_SPAN * Math.sqrt(Math.min(Math.max(pts, 0), MAX_PTS) / MAX_PTS)

const STATUS: Record<string, { letter: string; color: string }> = {
  Out: { letter: 'O', color: 'var(--critical)' },
  Doubtful: { letter: 'D', color: 'var(--critical)' },
  Questionable: { letter: 'Q', color: 'var(--warning)' },
}
const BADGE_INK: Record<string, string> = { O: '#fff', D: '#fff', Q: '#1b1f24' 
}

const pct = (p: number) => `${Math.round(100 * p)}%`
const pts = (v: number) => v.toFixed(1)

function Spot({ s, color, bind }: { s: LineupSpot; color: string; bind: ReturnType<typeof useChartTip>['bind'] }) {
  const xy = SPOTS[s.slot]
  if (!xy) return null
  const [x, y] = xy
  const valued = s.value_pts !== null
  const r = valued ? ringR(s.value_pts!) : R_MIN + 1.5
  const keep = s.status ? (s.p_play ?? 0) : 1 // share of the value expected to play
  const st = s.status ? STATUS[s.status] : undefined
  return (
    <g {...bind(s.slot)} data-slot={s.slot} data-status={s.status ?? undefined} aria-label={label(s)}>
      <circle cx={x} cy={y} r={Math.max(r, 10)} fill="transparent" />
      {valued ? (
        <>
          <circle cx={x} cy={y} r={r} fill="var(--surface-1)" stroke={color} strokeWidth={1.5} />
          {keep > 0 && <circle cx={x} cy={y} r={Math.max(r * Math.sqrt(keep), 1.5)} fill={color} />}
        </>
      ) : (
        <circle cx={x} cy={y} r={r} fill="var(--surface-1)" stroke="var(--text-muted)" strokeWidth={1.25} strokeDasharray="2 2" />
      )}
      {st && (
        <g data-badge={st.letter}>
          <circle cx={x + r * 0.75 + 2} cy={y - r * 0.75 - 2} r={7} fill={st.color} stroke="var(--surface-1)" strokeWidth={1.5} />
          <text x={x + r * 0.75 + 2} y={y - r * 0.75 + 1.2} textAnchor="middle" fontSize={9} fontWeight={700} fill={BADGE_INK[st.letter]}>{st.letter}</text>
        </g>
      )}
      <text x={x} y={y + Math.max(r, 5) + 9} textAnchor="middle" fontSize={8.5} fill="var(--text-muted)">{s.slot.replace(/[123]$/, '')}</text>
    </g>
  )
}

function label(s: LineupSpot) {
  const v = s.value_pts === null ? 'not valued yet' : `worth ${pts(s.value_pts)} points`
  return `${s.slot}: ${s.player}, ${v}${s.status ? `, ${s.status}` : ''}`
}

function Tip({ s }: { s: LineupSpot }) {
  return (
    <>
      <TipTitle note={`${s.slot}${s.grp ? ` · ${s.grp}` : ''}`}>{s.player}</TipTitle>
      {s.value_pts === null ? (
        <TipNote>No value yet: the model doesn&apos;t cover linebackers or interior linemen, or a player without enough games.</TipNote>
      ) : (
        <TipRow value={`${pts(s.value_pts)} pts`} label="worth to his team" />
      )}
      {s.status && <TipRow value={s.status} label="on this week's report" />}
      {s.status && s.p_play !== null && s.status !== 'Out' && <TipRow value={pct(s.p_play)} label={`of players listed ${s.status} have played`} />}
      {s.at_risk !== null && <TipRow value={`${pts(s.at_risk)} pts`} label="at risk" />}
    </>
  )
}

function Unit({ title, formation, spots, color }: { title: string; formation: string | null; spots: LineupSpot[]; color: string }) {
  const { box, at, bind, card } = useChartTip()
  const hovered = spots.find((s) => s.slot === at?.key)
  return (
    <figure className="min-w-0 max-w-[460px]">
      <figcaption className="mb-1 text-[12px] text-ink-3">
        <span className="font-medium text-ink-2">{title}</span>
        {formation && <span> · {formation}</span>}
      </figcaption>
      <div ref={box} className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="group" aria-label={`${title} starters`}>
          <rect x={0} y={0} width={W} height={H} rx={6} fill="var(--surface-2)" />
          <line x1={6} x2={W - 6} y1={LOS} y2={LOS} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="4 3" />
          {spots.map((s) => <Spot key={s.slot} s={s} color={color} bind={bind} />)}
        </svg>
        {hovered && card(<Tip s={hovered} />)}
      </div>
    </figure>
  )
}

export function FormationMap({ lineup, side }: { lineup: SideLineup; side: 'home' | 'away' }) {
  const color = `var(--team-${side})`
  return (
    <div data-testid={`formation-${side}`} className="grid gap-3">
      <p className="m-0 text-[12px] text-ink-3">Depth chart of {kickoffEt(lineup.chart_ts)}</p>
      <Unit title="Offense" formation={lineup.offense_formation} spots={lineup.offense} color={color} />
      <Unit title="Defense" formation={lineup.defense_formation} spots={lineup.defense} color={color} />
    </div>
  )
}

/** The key under the maps, once per page. */
export function FormationKey() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3">
      <span className="inline-flex items-center gap-1.5">
        <svg width={16} height={16} aria-hidden><circle cx={8} cy={8} r={6.5} fill="var(--surface-1)" stroke="var(--text-muted)" strokeWidth={1.5} /><circle cx={8} cy={8} r={4} fill="var(--text-muted)" /></svg>
        bigger ring = worth more; the empty part is at risk
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg width={14} height={14} aria-hidden><circle cx={7} cy={7} r={5} fill="none" stroke="var(--text-muted)" strokeWidth={1.25} strokeDasharray="2 2" /></svg>
        not valued yet
      </span>
      <span>Q, D, O: Questionable, Doubtful, Out</span>
    </div>
  )
}
