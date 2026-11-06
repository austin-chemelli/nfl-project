/** Pure helpers for the League page's context features (ADR 0019, M14 phase 3): similar seasons, two-team compare, rank table, odds history. */
import type { LeagueFile, SimilarNeighbour, SimilarTeam, TeamFeature, TeamsFile } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { groupFeatures, hasData, usableFeatures } from './helpers'
import { PRESETS } from './presets'
import { fmtProb, type View } from './playoffs'

// ------------------------------------------------------------------------------ similar seasons

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

export type SimilarTile = { key: string; label: string; value: string }

/** The tile row: how many of the nearest seasons made the playoffs, then reached each round or beyond. */
export function similarTiles(s: SimilarTeam): SimilarTile[] {
  const of = `of ${s.k_summary}`
  const tile = (key: string, label: string, n: number): SimilarTile => ({ key, label, value: `${n} ${of}` })
  return [
    tile('playoffs', 'Made the playoffs', s.made_playoffs),
    tile('div', 'Reached the divisional round', s.rounds.div),
    tile('conf', 'Reached the conference game', s.rounds.conf),
    tile('sb', 'Reached the Super Bowl', s.rounds.sb),
    tile('champ', 'Won the Super Bowl', s.rounds.champ),
  ]
}

/** "9 of 25 made the playoffs": the one-line summary. */
export function similarHeadline(s: SimilarTeam): string {
  return `${s.made_playoffs} of ${s.k_summary} made the playoffs`
}

export type SimilarRow = { key: string; season: number; team: string; then: string; final: string; outcome: string; playoffs: boolean }

export function similarRows(s: SimilarTeam): SimilarRow[] {
  return s.neighbours.map((n, i) => ({
    key: `${n.season}-${n.team}-${i}`,
    season: n.season,
    team: n.team,
    then: recordFrom(n.rec_then),
    final: recordFrom(n.final),
    outcome: outcomeText(n),
    playoffs: n.playoffs,
  }))
}

/** Teams of the league file in name order, flagged by whether they have a similar-seasons entry. */
export function similarOptions(file: LeagueFile): { code: string; name: string; has: boolean }[] {
  return file.teams
    .map((t) => ({ code: t.team, name: teamInfo(t.team).name || t.team, has: Object.hasOwn(file.similar, t.team) }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

/**
 * The team shown when none is picked: the Student's best chance of the playoffs among the teams that
 * have an entry, else the first with an entry by name, else null. Tied chances go by name.
 */
export function defaultSimilarTeam(file: LeagueFile): string | null {
  const opts = similarOptions(file).filter((o) => o.has)
  if (opts.length === 0) return null
  const p = (c: string) => file.odds.student.teams[c]?.playoffs ?? -1
  return [...opts].sort((a, b) => p(b.code) - p(a.code) || a.name.localeCompare(b.name))[0].code
}

/** The picked team if it is a team in the file (`hasOwn` on the entry map isn't enough: an entry may be missing by design), else the default. */
export function resolveSimilarTeam(file: LeagueFile, raw: string | null): string | null {
  if (raw && file.teams.some((t) => t.team === raw)) return raw
  return defaultSimilarTeam(file)
}

// ------------------------------------------------------------------------------------- compare

export type CompareRow = { feature: TeamFeature; a: number | null; b: number | null; rankA: number | null; rankB: number | null; edge: 'a' | 'b' | null }
export type CompareGroup = { name: string; rows: CompareRow[]; aAhead: number; bAhead: number }

/** Which side is better on a measure with a direction; null for a style measure, a missing value or a tie. */
export function edgeOf(f: Pick<TeamFeature, 'better'>, a: number | null, b: number | null): 'a' | 'b' | null {
  if (f.better == null || a == null || b == null || a === b) return null
  return (f.better === 'higher' ? a > b : a < b) ? 'a' : 'b'
}

/** Every published measure with a value for either team, in registry groups. Groups left empty are dropped. */
export function compareGroups(file: TeamsFile, a: string, b: string): CompareGroup[] {
  const ta = file.teams[a]
  const tb = file.teams[b]
  if (!ta || !tb) return []
  const out: CompareGroup[] = []
  for (const g of groupFeatures(usableFeatures(file))) {
    const rows: CompareRow[] = []
    for (const feature of g.features) {
      const va = ta.values[feature.id] ?? null
      const vb = tb.values[feature.id] ?? null
      if (va == null && vb == null) continue
      rows.push({ feature, a: va, b: vb, rankA: ta.rank?.[feature.id] ?? null, rankB: tb.rank?.[feature.id] ?? null, edge: edgeOf(feature, va, vb) })
    }
    if (rows.length) out.push({ name: g.name, rows, aAhead: rows.filter((r) => r.edge === 'a').length, bAhead: rows.filter((r) => r.edge === 'b').length })
  }
  return out
}

/** The axis for a row: the league's range with the better side on the right, so "right is better" holds wherever a measure has a direction. */
export function compareDomain(r: CompareRow): [number, number] {
  const f = r.feature
  const vals = [f.lo, f.hi, r.a, r.b].filter((v): v is number => v != null)
  let lo = Math.min(...vals)
  let hi = Math.max(...vals)
  if (lo === hi) { lo -= 0.5; hi += 0.5 }
  return f.better === 'lower' ? [hi, lo] : [lo, hi]
}

/** A valid second team: in the file and not the first. Otherwise null (an unknown `?vs=` is ignored). */
export function resolveVs(file: TeamsFile, team: string | null, raw: string | null): string | null {
  return team && raw && raw !== team && Object.hasOwn(file.teams, raw) ? raw : null
}

// --------------------------------------------------------------------------------------- ranks

/** The measures in the rank table: those the preset charts use, once each, in preset order, with data. */
export function rankColumns(file: TeamsFile): TeamFeature[] {
  const seen = new Set<string>()
  const out: TeamFeature[] = []
  for (const p of PRESETS) {
    for (const id of [p.x, p.y]) {
      if (seen.has(id) || !hasData(file, id)) continue
      seen.add(id)
      const f = file.features.find((o) => o.id === id)
      if (f) out.push(f)
    }
  }
  return out
}

export type RankSort = { key: 'team' | string; dir: 'ascending' | 'descending' }

/** First click on a measure puts the best team first; on Team, A to Z. */
export function firstSort(key: string, f?: TeamFeature): RankSort {
  if (key === 'team') return { key, dir: 'ascending' }
  return { key, dir: f?.better === 'lower' ? 'ascending' : 'descending' }
}

/** Teams sorted by name or by one measure's value, teams without a value last, ties by name. */
export function sortTeams(file: TeamsFile, sort: RankSort): string[] {
  const name = (c: string) => teamInfo(c).name || c
  const codes = Object.keys(file.teams)
  const sign = sort.dir === 'ascending' ? 1 : -1
  return codes.sort((x, y) => {
    if (sort.key === 'team') return sign * name(x).localeCompare(name(y))
    const vx = file.teams[x].values[sort.key]
    const vy = file.teams[y].values[sort.key]
    if (vx == null || vy == null) return vx == null && vy == null ? name(x).localeCompare(name(y)) : vx == null ? 1 : -1
    return sign * (vx - vy) || name(x).localeCompare(name(y))
  })
}

/** Shading strength 0 to 45 (percent of the color): the best team in the league gets the most, the worst none. Null without a rank. */
export function shadeFor(rank: number | undefined, n: number): number | null {
  if (rank == null || n < 2) return null
  return Math.round((45 * (n - rank)) / (n - 1))
}

// ------------------------------------------------------------------------------ odds history

export type SparkPoint = { week: number; value: number }

/** One team's P(playoffs) by week for the view shown; weeks without a value are left out. */
export function sparkSeries(file: LeagueFile, team: string, view: View): SparkPoint[] {
  const out: SparkPoint[] = []
  for (const h of Object.hasOwn(file.history, team) ? file.history[team] : []) {
    const value = h[view]
    if (value != null) out.push({ week: h.week, value })
  }
  return out.sort((a, b) => a.week - b.week)
}

/** The line is drawn from two points up. */
export const hasSpark = (points: SparkPoint[]) => points.length >= 2

export function sparkLabel(points: SparkPoint[]): string {
  const first = points[0]
  const last = points[points.length - 1]
  return `Chance of the playoffs by week: Week ${first.week} ${fmtProb(first.value)}, Week ${last.week} ${fmtProb(last.value)}`
}
