/**
 * Pure helpers for the Similar seasons tab (ADR 0019): finish grid, flag sentences, the overlap chart's
 * arithmetic. Descriptive only: nothing here says what a team "will" do.
 */
import type { LeagueFile, SimilarFile, SimilarFlag, SimilarNeighbour, SimilarTeam } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { ordinal } from './helpers'

/** "6-2" and "7-9-0" as "6–2" and "7–9": a trailing zero-tie count is dropped. */
export function recordFrom(raw: string): string {
  const parts = raw.split('-')
  if (parts.length === 3 && Number(parts[2]) === 0) parts.pop()
  return parts.join('–')
}

/** The furthest round a past team reached, in words. A missing round for a playoff team still reads as making it. */
export function outcomeText(n: Pick<SimilarNeighbour, 'playoffs' | 'round'>): string {
  if (!n.playoffs) return 'Missed the playoffs'
  switch (n.round) {
    case 'wc': return 'Lost in the wild-card round'
    case 'div': return 'Lost in the divisional round'
    case 'conf': return 'Lost the conference game'
    case 'sb': return 'Lost the Super Bowl'
    case 'champ': return 'Won the Super Bowl'
    default: return 'Made the playoffs'
  }
}

// ------------------------------------------------------------------------------------ finish grid

/** 0 missed, then wild card, divisional, conference game, Super Bowl, champion. */
export type Level = 0 | 1 | 2 | 3 | 4 | 5

export function finishLevel(n: Pick<SimilarNeighbour, 'playoffs' | 'round'>): Level {
  if (!n.playoffs) return 0
  switch (n.round) {
    case 'champ': return 5
    case 'sb': return 4
    case 'conf': return 3
    case 'div': return 2
    default: return 1
  }
}

/** Legend words, furthest round first. */
export const LEVEL_LABELS: Record<Level, string> = {
  5: 'Won the Super Bowl',
  4: 'Lost the Super Bowl',
  3: 'Lost the conference game',
  2: 'Lost the divisional round',
  1: 'Lost the wild-card round',
  0: 'Missed the playoffs',
}

/** "2018 KC, 12-4, lost the conference game": what a grid square or a chart dot names. */
export function seasonLabel(n: SimilarNeighbour): string {
  const o = outcomeText(n)
  return `${n.season} ${n.team}, ${recordFrom(n.final)}, ${o.charAt(0).toLowerCase()}${o.slice(1)}`
}

export type GridCell = { index: number; level: Level; n: SimilarNeighbour; label: string }

/** One cell per nearest season, furthest round first; within a round the nearer season first. */
export function finishGrid(nearest: SimilarNeighbour[]): GridCell[] {
  return nearest
    .map((n, index) => ({ index, level: finishLevel(n), n, label: seasonLabel(n) }))
    .sort((a, b) => b.level - a.level || a.index - b.index)
}

/** Counts per level for the legend, furthest first; levels nobody reached are kept with a zero. */
export function levelCounts(cells: GridCell[]): { level: Level; label: string; count: number }[] {
  return ([5, 4, 3, 2, 1, 0] as Level[]).map((level) => ({ level, label: LEVEL_LABELS[level], count: cells.filter((c) => c.level === level).length }))
}

// -------------------------------------------------------------------------------------- the list

export const LISTED = 10

const labelOf = (measures: SimilarFile['measures'], id: string) => measures.find((m) => m.id === id)?.label ?? id

/** "Closest on Record, QB play · furthest on Defense"; empty parts are left out, and null with neither. */
export function closestText(n: Pick<SimilarNeighbour, 'closest' | 'furthest'>, measures: SimilarFile['measures']): string | null {
  const join = (ids: string[]) => ids.map((id) => labelOf(measures, id)).join(', ')
  const parts = [n.closest.length ? `Closest on ${join(n.closest)}` : '', n.furthest.length ? `${n.closest.length ? 'f' : 'F'}urthest on ${join(n.furthest)}` : ''].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

export type SimilarRow = { key: string; index: number; season: number; team: string; then: string; final: string; outcome: string; playoffs: boolean; close: string | null }

/** The ten nearest, as rows. `index` is the position in `nearest`, which the chart shares. */
export function similarRows(s: SimilarTeam, measures: SimilarFile['measures']): SimilarRow[] {
  return s.nearest.slice(0, LISTED).map((n, i) => ({
    key: `${n.season}-${n.team}-${i}`,
    index: i,
    season: n.season,
    team: n.team,
    then: recordFrom(n.rec_then),
    final: recordFrom(n.final),
    outcome: outcomeText(n),
    playoffs: n.playoffs,
    close: closestText(n, measures),
  }))
}

// ----------------------------------------------------------------------------------- the picker

/** Teams of the league file in name order, flagged by whether the similar file has an entry. */
export function similarOptions(league: LeagueFile, sim: SimilarFile | null): { code: string; name: string; has: boolean }[] {
  return league.teams
    .map((t) => ({ code: t.team, name: teamInfo(t.team).name || t.team, has: !!sim && Object.hasOwn(sim.teams, t.team) }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

/** The Student's best chance of the playoffs among the teams with an entry, else the first by name, else null. */
export function defaultSimilarTeam(league: LeagueFile, sim: SimilarFile | null): string | null {
  const opts = similarOptions(league, sim).filter((o) => o.has)
  if (opts.length === 0) return null
  const p = (c: string) => league.odds.student.teams[c]?.playoffs ?? -1
  return [...opts].sort((a, b) => p(b.code) - p(a.code) || a.name.localeCompare(b.name))[0].code
}

/** The picked team if it is a team in the league file (an entry may be missing by design), else the default. */
export function resolveSimilarTeam(league: LeagueFile, sim: SimilarFile | null, raw: string | null): string | null {
  if (raw && league.teams.some((t) => t.team === raw)) return raw
  return defaultSimilarTeam(league, sim) ?? league.teams[0]?.team ?? null
}

// ------------------------------------------------------------------------------------ flag cards

const suffix = (id: string) => id.split('.').pop() ?? id
const lower1 = (s: string) => (s.length > 0 ? s.charAt(0).toLowerCase() + s.slice(1) : s)

/** What the flagged teams had, per measure and quarter, in the words of "those with ___". One template each so each reads naturally. */
function trait(f: Pick<SimilarFlag, 'measure' | 'label' | 'quarter'>): string {
  const q = `${f.quarter}-quarter`
  const id = suffix(f.measure)
  if (/turnover/.test(id)) return `a ${q} turnover margin`
  switch (id) {
    case 'epa_off_adj': return `a ${q} offense`
    case 'epa_def': return `a ${q} defense`
    case 'qb_epa': return `${q} QB play`
    case 'pythag_win_pct': return `a ${q} expected win rate`
    case 'point_diff_pg': return `a ${q} point margin per game`
    case 'elo_pre': return `a ${q} long-run rating`
    case 'last3_win_pct': return `a ${q} record over their last three games`
    case 'streak': return `a ${q} streak`
    case 'luck': return 'a scoring margin better than their record'
    default: return `a ${q} ${lower1(f.label)}`
  }
}

const VERB = { made: 'made the playoffs', conf: 'reached the conference championship game' } as const

/** Under this many past teams on either side, a card gets a "small sample" note. */
export const SMALL = 20

export type FlagCard = { key: string; kind: SimilarFlag['kind']; title: string; lead: string | null; body: string; /** What the counts count, said on the card: "Made the playoffs, teams at 6-2". */ counts: string; verdict: string; note: string | null; flagged: [number, number]; others: [number, number]; /** Either count's denominator is under SMALL: the share could be noise. */ small: boolean }

/** How the flagged share compares with the rest, from the counts alone, so it can't contradict them. */
export function shareVerdict(f: Pick<SimilarFlag, 'flagged' | 'others'>): string {
  const a = f.flagged[1] > 0 ? f.flagged[0] / f.flagged[1] : 0
  const b = f.others[1] > 0 ? f.others[0] / f.others[1] : 0
  if (a - b <= -0.02) return 'A smaller share than the rest'
  if (a - b >= 0.02) return 'A larger share than the rest'
  return 'About the same share as the rest'
}

/** Measures with few possible values: many teams tie, so a printed rank wouldn't match its quarter. */
const TIES = new Set(['last3_win_pct', 'streak'])

/** The sentence for one flag; the card shows it as a hover and prints the counts. Always teams on exactly this record: nothing here says a measure matters, or doesn't, on its own. */
export function flagCard(f: SimilarFlag, i = 0): FlagCard {
  const id = suffix(f.measure)
  const luck = id === 'luck'
  const body = `Among past teams at ${f.peers}, those with ${trait(f)} ${VERB[f.outcome]} ${f.flagged[0]} of ${f.flagged[1]} times, against ${f.others[0]} of ${f.others[1]} for the rest.`
  return {
    key: `${f.kind}-${f.measure}-${i}`,
    kind: f.kind,
    title: luck ? 'Record undersells them.' : TIES.has(id) ? `${f.label}.` : `${f.label}: ${ordinal(f.rank)}.`,
    lead: luck ? 'Their scoring margin is better than their record.' : null,
    body,
    counts: `${VERB[f.outcome].charAt(0).toUpperCase()}${VERB[f.outcome].slice(1)}, teams at ${f.peers}`,
    verdict: shareVerdict(f),
    note: f.kind === 'fine' && !luck ? "This compares teams on the same record. It doesn't say the measure stops mattering." : null,
    flagged: f.flagged,
    others: f.others,
    small: f.flagged[1] < SMALL || f.others[1] < SMALL,
  }
}

/** Why a team has no cards. "Nothing stands out" would be untrue for a team the record alone has settled. */
export function noCards(gamesPlayed: number, record: string, peers: { made: number; n: number } | null): string {
  if (gamesPlayed < 6) return 'These cards start at six games, the earliest point tested.'
  if (gamesPlayed > 12) return 'These cards stop after 12 games: late in a season these patterns fade, and the record says most of it.'
  if (peers && peers.made === 0) return `No past team at ${record} made the playoffs, so nothing separates them.`
  if (peers && peers.made === peers.n) return `Every past team at ${record} made the playoffs, so nothing separates them.`
  return 'Nothing on our list of measures stands out for this team against past teams on the same record.'
}

export const FLAG_GROUPS: { kind: SimilarFlag['kind']; title: string }[] = [
  { kind: 'red', title: 'Red flags' },
  { kind: 'fine', title: "Looks bad, wasn't" },
  { kind: 'strength', title: 'Real strengths' },
]

/** The three groups in order, empty ones left out. */
export function flagGroups(flags: SimilarFlag[]): { kind: SimilarFlag['kind']; title: string; cards: FlagCard[] }[] {
  return FLAG_GROUPS.map((g) => ({ ...g, cards: flags.filter((f) => f.kind === g.kind).map((f, i) => flagCard(f, i)) })).filter((g) => g.cards.length > 0)
}

// ----------------------------------------------------------------------------------- overlap chart

/**
 * Vertical lane for each dot on a strip, so close dots don't sit on one another: 0, +1, -1, +2, -2,
 * taking the first lane whose last dot is at least `gap` away. Dots are placed left to right, ties by
 * position in the list, so the same data always lays out the same way.
 */
export function laneOffsets(xs: number[], gap: number): number[] {
  const order = xs.map((_, i) => i).sort((a, b) => xs[a] - xs[b] || a - b)
  const last = new Map<number, number>()
  const out = new Array<number>(xs.length).fill(0)
  for (const i of order) {
    let k = 0
    for (;;) {
      const lane = k === 0 ? 0 : k % 2 === 1 ? (k + 1) / 2 : -k / 2
      const prev = last.get(lane)
      if (prev === undefined || xs[i] - prev >= gap) {
        last.set(lane, xs[i])
        out[i] = lane
        break
      }
      k++
    }
  }
  return out
}

/** Linear quantile of values (q in 0..1). */
export function quantile(values: number[], q: number): number {
  const s = [...values].sort((a, b) => a - b)
  if (s.length === 0) return NaN
  const pos = (s.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return s[lo] + (s[hi] - s[lo]) * (pos - lo)
}

export type RowSpread = { lo: number; hi: number; width: number; tight: 'tight' | 'moderate' | 'loose' }

/** The middle half of the nearest seasons on one measure: the faint band, and how tight it is. */
export function rowSpread(values: number[], mine?: number | null): RowSpread | null {
  const v = values.filter((x) => Number.isFinite(x))
  if (v.length < 4) return null
  const lo = quantile(v, 0.25)
  const hi = quantile(v, 0.75)
  // how close the seasons sit to this team, not how narrow they are: percentiles bunch up at the ends
  const off = mine == null ? hi - lo : quantile(v.map((x) => Math.abs(x - mine)), 0.5)
  const near = mine == null ? 15 : 10
  return { lo, hi, width: hi - lo, tight: off <= near ? 'tight' : off <= 2 * near ? 'moderate' : 'loose' }
}

export const spreadText = (s: RowSpread) => `middle half ${Math.round(s.lo)} to ${Math.round(s.hi)}`

/** Screen-reader summary of the chart: this team's percentile and the nearest seasons' middle half, per measure. */
export function overlapSummary(entry: SimilarTeam, measures: SimilarFile['measures'], name: string): string {
  const rows = measures.map((m, i) => {
    const mine = entry.profile[i]
    const sp = rowSpread(entry.nearest.map((n) => n.profile[i]).filter((v) => v != null))
    return `${m.label} ${mine == null ? 'no value' : Math.round(mine)}${sp ? `, nearest seasons ${Math.round(sp.lo)} to ${Math.round(sp.hi)}` : ''}`
  })
  return `Where the ${name} and their ${entry.nearest.length} nearest seasons sit on seven measures, as percentiles from 0 to 100. ${rows.join('. ')}.`
}

// -------------------------------------------------------------------------------------- fine print

/** "2002 to 2025", from the file's pool, so it stays true late in a season when the 16-game window starts later. */
export function poolYears(pool: SimilarTeam['pool']): string | null {
  return pool ? `${pool.seasons[0]} to ${pool.seasons[1]}` : null
}
