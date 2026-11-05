/** Pure helpers for the Slate page (port of nfl.ui.slate_helpers). */
import type { CardData, GameRow, Meta } from '../../data/contract'
import { APPROACHES, HEADLINE, REFERENCES, SHORT } from '../../lib/models'
import { pct } from '../../lib/format'
import { edgePct, groupOf } from '../../lib/meta'
import { injuryRank, ordinal } from '../game/helpers'
import { topAbsence, topEdge } from '../game/summary'

/** |model − market| in probability at which a cell is highlighted. */
export const DIVERGE = 0.05

export type Pick = { team: string; p: number; pHome: number; div: number | null; home: boolean }

/** The side a model favors, its win probability and its divergence from the market. */
export function pickOf(game: GameRow, mid: string): Pick | null {
  const m = game.models[mid]
  if (!m || m.p_home == null) return null
  const home = m.p_home >= 0.5
  return { team: home ? game.home : game.away, p: home ? m.p_home : 1 - m.p_home, pHome: m.p_home, div: m.divergence, home }
}

export function homeWon(game: GameRow): boolean | null {
  const m = game.result?.margin
  return m == null || m === 0 ? null : m > 0
}

/** Did this model pick the winner? null while unplayed (or a tie). */
export function correct(game: GameRow, mid: string): boolean | null {
  const pk = pickOf(game, mid)
  const won = homeWon(game)
  return pk == null || won == null ? null : pk.home === won
}

/** The game's status from its headline line, else in a fixed order, so it never depends on key order. */
export function gameStatus(game: GameRow): { status: string; lockTs: string | null } {
  const m = [HEADLINE, ...APPROACHES, ...REFERENCES].map((id) => game.models[id]).find((x) => x != null)
  return m ? { status: m.status, lockTs: m.lock_ts } : { status: 'none', lockTs: null }
}

export function scoreText(game: GameRow): string {
  const r = game.result
  return r ? `${game.away} ${r.away_score}, ${game.home} ${r.home_score}` : ''
}

export function sideText(game: GameRow, pHome: number): string {
  const home = pHome >= 0.5
  return `${home ? game.home : game.away} ${pct(home ? pHome : 1 - pHome)}`
}

/** Plain-words divergence: "6 pts more on GB than the market". */
export function divergenceText(div: number, game: GameRow): string {
  return `${Math.round(Math.abs(div) * 100)} pts more on ${div > 0 ? game.home : game.away} than the market`
}

export type Disagreement = { game: GameRow; spread: number; hi: string; lo: string; ps: Record<string, number> }

/** Top-n games by the gap between the four approaches' home win chance (max − min). */
export function disagreements(games: GameRow[], n = 3): Disagreement[] {
  const out: Disagreement[] = []
  for (const g of games) {
    const ps: Record<string, number> = {}
    for (const a of APPROACHES) {
      const p = g.models[a]?.p_home
      if (p != null) ps[a] = p
    }
    const ids = Object.keys(ps)
    if (ids.length < 2) continue
    const hi = ids.reduce((x, y) => (ps[y] > ps[x] ? y : x))
    const lo = ids.reduce((x, y) => (ps[y] < ps[x] ? y : x))
    out.push({ game: g, spread: ps[hi] - ps[lo], hi, lo, ps })
  }
  return out.sort((a, b) => b.spread - a.spread).slice(0, n)
}

export const byKickoff = (games: GameRow[]) => [...games].sort((a, b) => (a.kickoff_utc || '').localeCompare(b.kickoff_utc || ''))

/** Weeks list with the previous/next neighbours of `week`. */
export function neighbours(weeks: number[], week: number): { prev: number | null; next: number | null } {
  const ws = [...weeks].sort((a, b) => a - b)
  const i = ws.indexOf(week)
  if (i < 0) return { prev: null, next: null }
  return { prev: ws[i - 1] ?? null, next: ws[i + 1] ?? null }
}

/** The current week lives at `/`; every other week has an explicit URL. */
export const weekHref = (meta: Meta, season: number, week: number) =>
  season === meta.season && week === meta.current_week ? '/' : `/week/${season}/${week}`

// ------------------------------------------------------------------------------- cards (ADR 0017)

export type SortKey = 'kickoff' | 'disagreement' | 'upset'
export const SORTS: { value: SortKey; label: string }[] = [
  { value: 'kickoff', label: 'Kickoff' },
  { value: 'disagreement', label: 'Student vs market' },
  { value: 'upset', label: 'Upset' },
]
export const parseSort = (s: string | null): SortKey => (SORTS.some((o) => o.value === s) ? (s as SortKey) : 'kickoff')

/** Within 5 points of 50% is a toss-up, not an upset or a clear favorite. */
const TOSS_UP = 0.05

const approachPs = (g: GameRow): { id: string; p: number }[] =>
  APPROACHES.flatMap((a) => {
    const p = g.models[a]?.p_home
    return p == null ? [] : [{ id: a, p }]
  })

/** |headline approach − market| in home win chance; null if either is missing. */
export function gapToMarket(g: GameRow): number | null {
  const m = g.models[HEADLINE]?.p_home
  const mk = g.market?.p_home
  return m == null || mk == null ? null : Math.abs(m - mk)
}

/** The market's pregame win chance for the team that won; null while unplayed, on a tie or with no line. */
export function winnerMarketP(g: GameRow): number | null {
  const won = homeWon(g)
  const mk = g.market?.p_home
  return won == null || mk == null ? null : won ? mk : 1 - mk
}

/** Games in display order; ties keep kickoff order. Upset: finished games, the winner's lowest market chance first, then the rest. */
export function sortGames(games: GameRow[], sort: SortKey): GameRow[] {
  const base = byKickoff(games)
  if (sort === 'kickoff') return base
  const key = (g: GameRow) => (sort === 'disagreement' ? (gapToMarket(g) == null ? null : -gapToMarket(g)!) : winnerMarketP(g))
  return base
    .map((g, i) => ({ g, i, k: key(g) }))
    .sort((a, b) => (a.k == null || b.k == null ? Number(a.k == null) - Number(b.k == null) : a.k - b.k) || a.i - b.i)
    .map((x) => x.g)
}

const short = (id: string) => SHORT[id] ?? id
const names = (ids: string[]) => (ids.length <= 1 ? ids.map(short).join('') : `${ids.slice(0, -1).map(short).join(', ')} and ${short(ids[ids.length - 1])}`)

/** One plain line for a matchup card, computed from the row. */
export function cardSentence(g: GameRow): string {
  const ps = approachPs(g)
  if (ps.length === 0) return 'Not scored yet'
  const won = homeWon(g)
  if (g.result != null) return finishedSentence(g, ps, won)
  const onHome = ps.filter((x) => x.p >= 0.5)
  const onAway = ps.filter((x) => x.p < 0.5)
  if (onHome.length > 0 && onAway.length > 0) {
    if (onHome.length === onAway.length) return `Approaches split ${onHome.length}–${onAway.length}`
    const [major, minor, side, other] = onHome.length > onAway.length ? [onHome, onAway, g.home, g.away] : [onAway, onHome, g.away, g.home]
    return `Split ${major.length}–${minor.length} ${side}; ${names(minor.map((x) => x.id))} ${minor.length === 1 ? 'takes' : 'take'} ${other}`
  }
  const side = onHome.length ? g.home : g.away
  const n = ps.length === 4 ? 'All four' : `All ${ps.length}`
  const mk = g.market?.p_home
  if (mk == null) return `${n} pick ${side}`
  if ((mk >= 0.5) !== (side === g.home)) return `${n} pick ${side}; the market leans ${mk >= 0.5 ? g.home : g.away}`
  const far = ps.reduce((a, b) => (Math.abs(b.p - mk) > Math.abs(a.p - mk) ? b : a))
  const gap = Math.round(100 * Math.abs(far.p - mk))
  if (Math.abs(far.p - mk) >= DIVERGE) return `${short(far.id)} is ${gap} pts from the market on ${far.p > mk ? g.home : g.away}`
  return `${n} agree with the market`
}

function finishedSentence(g: GameRow, ps: { id: string; p: number }[], won: boolean | null): string {
  if (won == null) return 'Ended in a tie'
  const winner = won ? g.home : g.away
  const loser = won ? g.away : g.home
  const pW = winnerMarketP(g)
  if (pW != null && pW < 0.5 - TOSS_UP) return `Upset: ${winner} won as a ${pct(pW)} underdog`
  const right = ps.filter((x) => (x.p >= 0.5) === won).map((x) => x.id)
  const n = ps.length === 4 ? 'All four' : `All ${ps.length}`
  if (right.length === ps.length) return `${n} picked ${winner}`
  if (right.length === 0) return `${n} picked ${loser}; ${winner} won`
  if (right.length <= ps.length / 2) return `${names(right)} called it`
  return `${names(ps.filter((x) => !right.includes(x.id)).map((x) => x.id))} missed it`
}

// ------------------------------------------------------------------- why this game (U4)

/** An edge must beat this share of matchups to be worth a card's line. */
const EDGE_MIN_PCT = 75
const WEATHER_MIN = 0.5

/** Names compare without suffixes or punctuation: the depth chart has `Gardner Minshew II`, the schedule `Gardner Minshew`. */
const sameQb = (a: string, b: string) => {
  const key = (s: string) => s.toLowerCase().replace(/[.'’]/g, '').replace(/\s+(jr|sr|ii|iii|iv)$/, '').trim()
  return key(a) === key(b)
}

/**
 * The QB news for one team, or null. Neither source is reliable alone: replayed days out, the
 * schedule's projected name and the depth chart each named the wrong man in about a third of the
 * lines they would have printed. So this needs both. It says "listed" when they agree and "unclear"
 * when they don't, and nothing once the game kicks off, when the chart is no longer read. A hurt
 * player is out of the running: his absence says that better, and the other source may have the
 * real story. `usual` comes back when the line names him, so the absence doesn't repeat it.
 */
function qbPiece(team: string, schedule: string | null, charted: string | null, usual: string | null, last: string | null, injuries: CardData['injuries']): { text: string; namesUsual: boolean } | null {
  if (!schedule || !charted) return null
  const hurt = (name: string) => injuries.some((i) => i.team === team && sameQb(i.player, name))
  const names = [charted, schedule].filter((n) => !hurt(n))
  if (names.length === 2 && !sameQb(charted, schedule)) return { text: `${team} starter unclear: ${charted} on the depth chart, ${schedule} on the schedule`, namesUsual: false }
  const listed = names[0]
  if (!listed || !usual || sameQb(listed, usual) || (last && sameQb(listed, last))) return null
  return { text: `${listed} listed to start for ${team} (usually ${usual})`, namesUsual: true }
}

/** One line on why a pregame matchup is worth a look, from `g.card`: up to two pieces, most newsworthy first. */
export function whyLine(g: GameRow, meta: Meta): string | null {
  const c = g.card
  if (g.result != null || c == null) return null
  const pieces: string[] = []

  // 1. QB news, this week only: a name further out is a guess
  const named = new Set<string>()
  if (g.week === meta.current_week) {
    for (const [team, schedule, side] of [[g.away, g.away_qb, 'away'], [g.home, g.home_qb, 'home']] as const) {
      const piece = qbPiece(team, schedule, c.charted_qb[side], c.usual_qb[side], c.last_qb[side], c.injuries)
      if (piece) pieces.push(piece.text)
      if (piece?.namesUsual && c.usual_qb[side]) named.add(c.usual_qb[side])
    }
  }

  // 2. A starter newly out: not a backup, and not someone gone for weeks
  const absence = topAbsence(c.injuries.filter((i) => i.starter && i.new && !named.has(i.player)))
  if (absence) {
    const i = absence.top
    pieces.push(injuryRank(i.status) === 0 ? `${i.team} without ${i.player}${i.pos ? ` (${i.pos})` : ''}` : `${i.team}'s ${i.player} doubtful`)
  }

  // 3. A game away from either home
  if (g.neutral_site) pieces.push(g.stadium ? `Neutral site: ${g.stadium}` : 'Neutral site')

  // 4. The biggest edge, when it is big
  const edge = topEdge(c.edges, meta, g.neutral_site)
  if (edge && edge.strength_pct >= EDGE_MIN_PCT) {
    pieces.push(`${edge.favors} ${groupOf(meta, edge.id)?.name ?? edge.id} edge, bigger than ${edgePct(edge.strength_pct)}% of matchups`)
  }

  // 5. Weather, only where it can matter
  if ((g.roof === 'outdoors' || g.roof === 'open') && (c.weather_concern ?? 0) >= WEATHER_MIN) pieces.push('Weather could be a factor')

  if (pieces.length > 0) return pieces.slice(0, 2).join(' · ')
  return edge ? 'No standout edge' : null
}

/** `The league's 3rd-most pass-heavy offense (JAX) faces its most blitz-heavy defense (BAL)`; null when nothing is stark. */
export function contrastLine(g: GameRow): string | null {
  const x = g.card?.contrast
  if (g.result != null || !x) return null
  const rank = (n: number) => (n === 1 ? 'most' : `${ordinal(n)}-most`)
  return `The league's ${rank(x.off_rank)} ${x.off_label} offense (${x.offense}) faces its ${rank(x.def_rank)} ${x.def_label} defense (${x.defense})`
}
