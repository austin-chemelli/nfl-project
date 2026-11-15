/** Shared words for team health (M24.7): group names, when a player can be back, his badge. */
import type { HealthStarter, RoomGrade } from '../data/contract'

export const GROUP: Record<string, string> = {
  QB: 'Quarterback', RB: 'Running back', WR: 'Receivers', TE: 'Tight end', OL: 'Offensive line',
  EDGE: 'Edge rushers', DL: 'Interior line', LB: 'Linebackers', CB: 'Cornerbacks', S: 'Safeties',
}
export const GROUP_ORDER = ['QB', 'RB', 'WR', 'TE', 'OL', 'EDGE', 'DL', 'LB', 'CB', 'S']

type Status = Pick<HealthStarter, 'status' | 'reserve' | 'since_week' | 'eligible_week'>

/** "IR since Wk 9 · eligible Wk 13", "Out", "IR since camp · no return window". */
export function whenBack(s: Status, week: number): string {
  if (!s.reserve) return s.status ?? ''
  const since = s.since_week == null ? '' : s.since_week <= 1 ? ' since camp' : ` since Wk ${s.since_week}`
  if (s.eligible_week == null) return `${s.status}${since} · no return window`
  if (s.eligible_week <= week) return `${s.status}${since} · eligible now`
  return `${s.status}${since} · eligible Wk ${s.eligible_week}`
}

/** How a starter shows: out (won't play), iffy (Questionable or Doubtful), doubt (hurt in practice
 * before Friday), or in. */
export type Tone = 'out' | 'iffy' | 'doubt' | 'in'
export function tone(s: Pick<HealthStarter, 'status' | 'p_play' | 'doubt'>): Tone {
  if (s.status == null) return 'in'
  if (s.doubt) return 'doubt'
  return s.p_play <= 0 ? 'out' : s.p_play < 1 ? 'iffy' : 'in'
}

/** The short badge on a ring: IR, PUP, O, D, Q, ? (practice), INA. */
export function badge(s: Pick<HealthStarter, 'status' | 'reserve' | 'doubt'>): string | null {
  if (s.status == null) return null
  if (s.doubt) return '?'
  if (s.reserve) return s.status.startsWith('PUP') ? 'PUP' : s.status.startsWith('IR') ? 'IR' : 'RES'
  return ({ Out: 'O', Doubtful: 'D', Questionable: 'Q', Inactive: 'INA' } as Record<string, string>)[s.status] ?? '!'
}

/** Who plays if he can't: the next man on the chart at his spot, else the starter he displaced. */
export const stepsIn = (s: HealthStarter): string | null => s.depth[0]?.player ?? s.replaced_by

/** "Puka Nacua" -> "Nacua"; keeps suffixes with the name ("Marvin Harrison Jr." -> "Harrison Jr."). */
export function lastName(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length < 2) return name
  const tail = parts[parts.length - 1]
  return /^(Jr\.?|Sr\.?|II|III|IV|V)$/.test(tail) && parts.length > 2 ? `${parts[parts.length - 2]} ${tail}` : tail
}

/** "5 starters out, 3 of them key players" */
export function outLine(out: number, keyOut: number): string {
  if (out === 0) return 'no starters out'
  const k = keyOut === 0 ? '' : keyOut === out ? (out === 1 ? ', a key player' : ', all key players') : `, ${keyOut} of them key`
  return `${out} starter${out === 1 ? '' : 's'} out${k}`
}

/** The share of a unit's spot weight that is available (team health, one unit). */
export function unitHealth(spots: Pick<HealthStarter, 'weight' | 'p_play'>[]): number | null {
  const full = spots.reduce((a, s) => a + s.weight, 0)
  if (full <= 0) return null
  return 1 - spots.reduce((a, s) => a + s.weight * (1 - s.p_play), 0) / full
}

/** "Receivers fall from #2 at full strength to about #24 now." The room that falls furthest. */
export function roomsLede(rooms: RoomGrade[]): string {
  const worst = [...rooms].sort((a, b) => (b.now_rank - b.rank) - (a.now_rank - a.rank))[0]
  if (!worst || worst.now_rank - worst.rank < 3) return 'How each room has played against the league. No room is missing enough to move far.'
  return `Biggest drop: ${(GROUP[worst.grp] ?? worst.grp).toLowerCase()}, #${worst.rank} at full strength to about #${worst.now_rank} now.`
}
