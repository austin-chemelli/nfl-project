/** Summary-strip tiles for the League page (ADR 0017): pure functions of `league.json`, each null when the file can't answer. */
import type { LeagueFile, LeagueGame } from '../../data/contract'
import { nextWeek, upcoming, type Conf } from './playoffs'

const confTeams = (file: LeagueFile, conf: Conf) => file.teams.filter((t) => t.conf === conf)

/** The conference's best chance at the 1 seed under the Student: its team and P(seed 1). */
export function topSeed(file: LeagueFile, conf: Conf): { team: string; p: number } | null {
  let best: { team: string; p: number } | null = null
  for (const t of confTeams(file, conf)) {
    const p = file.odds.student.teams[t.team]?.seed[0]
    if (p != null && (best == null || p > best.p)) best = { team: t.team, p }
  }
  return best
}

/**
 * The closest race: the division whose favourite has the lowest P(division) under the Student, so the
 * one nobody is likely to win. Reports the favourite and the runner-up. Divisions with one team in the odds are skipped.
 */
export function closestRace(file: LeagueFile): { division: string; leader: { team: string; p: number }; runnerUp: { team: string; p: number } } | null {
  let best: ReturnType<typeof closestRace> = null
  for (const division of new Set(file.teams.map((t) => t.div))) {
    const ranked = file.teams
      .filter((t) => t.div === division && file.odds.student.teams[t.team])
      .map((t) => ({ team: t.team, p: file.odds.student.teams[t.team].division }))
      .sort((a, b) => b.p - a.p || a.team.localeCompare(b.team))
    if (ranked.length < 2) continue
    if (best == null || ranked[0].p < best.leader.p) best = { division, leader: ranked[0], runnerUp: ranked[1] }
  }
  return best
}

/** The game of the week: the highest `leverage_total` among the earliest week's games. */
export function gameOfWeek(file: LeagueFile, now: number = Date.now()): LeagueGame | null {
  const ahead = upcoming(file.games, now)
  const week = nextWeek(ahead, now)
  const games = ahead.filter((g) => g.week === week)
  return games.reduce<LeagueGame | null>((best, g) => (best == null || g.leverage_total > best.leverage_total ? g : best), null)
}
