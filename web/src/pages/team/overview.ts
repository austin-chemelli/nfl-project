/** Pure logic for the Overview tab (ADR 0022, M18.3): where a team stands, and its best and worst ranks. */
import type { LeagueFile, LeagueOddsTeam, TeamFeature, TeamsFile } from '../../data/contract'
import { sparkSeries, type SparkPoint } from '../league/context'
import { recordOf } from '../league/playoffs'

export type Extreme = { feature: TeamFeature; rank: number; of: number; value: number | null; /** 0 = last in the league, 1 = first. */ place: number }
export type Extremes = { best: Extreme[]; worst: Extreme[] }

const GROUP = 3

/**
 * The best and worst ranks among measures with a direction. A style measure (`better` null), a missing
 * rank or a non-finite one is skipped. Ties keep registry order. With fewer than six ranked measures the
 * list is split so none is in both groups: the best half first, the worst gets the rest.
 */
export function extremes(file: TeamsFile, code: string): Extremes {
  const row = Object.hasOwn(file.teams, code) ? file.teams[code] : undefined
  if (!row?.rank) return { best: [], worst: [] }
  const all: Extreme[] = []
  for (const feature of file.features) {
    if (feature.better == null) continue
    const rank = row.rank[feature.id]
    if (rank == null || !Number.isFinite(rank) || rank < 1) continue
    const of = Math.max(feature.n, rank, 1)
    all.push({ feature, rank, of, value: row.values[feature.id] ?? null, place: of > 1 ? 1 - (rank - 1) / (of - 1) : 1 })
  }
  // a stable sort keeps registry order within a tie
  const sorted = all.sort((a, b) => a.rank - b.rank)
  const nb = Math.min(GROUP, Math.ceil(sorted.length / 2))
  const nw = Math.min(GROUP, sorted.length - nb)
  return { best: sorted.slice(0, nb), worst: nw > 0 ? sorted.slice(sorted.length - nw).reverse() : [] }
}

export type Standing = {
  record: string
  seed: number | null
  divRank: number
  /** Null after the regular season, when the odds entry is gone. */
  odds: LeagueOddsTeam | null
  /** True when the Student has no odds for any team: the season is over. */
  over: boolean
  total: number
  spark: SparkPoint[]
}

/** Null when the league file has no row for the team. */
export function standing(league: LeagueFile, code: string): Standing | null {
  const t = league.teams.find((o) => o.team === code)
  if (!t) return null
  const teams = league.odds.student.teams
  const odds = Object.hasOwn(teams, code) ? teams[code] : null
  return {
    record: recordOf(t),
    seed: t.seed_today,
    divRank: t.div_rank,
    odds,
    over: Object.keys(teams).length === 0,
    total: t.w + t.l + t.t + t.left,
    spark: odds ? sparkSeries(league, code, 'student') : [],
  }
}

/** Where a value sits on a 0 to `total` axis, as a percent kept inside the track. */
export const pctOf = (v: number, total: number) => (total > 0 ? Math.min(100, Math.max(0, (100 * v) / total)) : 0)
