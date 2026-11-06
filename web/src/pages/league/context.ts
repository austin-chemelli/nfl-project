/** Pure helpers for the League page's context features (ADR 0019, M14 phase 3): two-team compare, rank table, odds history. */
import type { LeagueFile, TeamFeature, TeamsFile } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { groupFeatures, hasData, usableFeatures } from './helpers'
import { PRESETS } from './presets'
import { fmtProb, type View } from './playoffs'

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

/**
 * The axis for a row: the league's true range on this measure (min and max over every team, not the
 * p10 and p90 the registry keeps), so a value sits in the same place whoever it is compared with, and the
 * better side on the right where a measure has a direction.
 */
export function compareDomain(file: TeamsFile, r: CompareRow): [number, number] {
  const f = r.feature
  const vals = [...Object.values(file.teams).map((t) => t.values[f.id]), r.a, r.b].filter((v): v is number => v != null)
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
