/** The engine's input from league.json (M26.2): played results, one source's game odds and its playoff ratings. */
import type { LeagueFile } from '../../data/contract'
import { fromScores } from './standings'
import type { SimInput } from './simulate'

export type Source = 'student' | 'market'

/**
 * Null when the file can't drive a what-if: no game left, no ratings (a file from before M26.2),
 * results missing for weeks already played, or a game without this source's chance.
 */
export function simInputFrom(file: LeagueFile, source: Source): SimInput | null {
  const v = file.odds[source]
  if (file.games.length === 0 || Object.keys(v.ratings).length === 0) return null
  if (file.played.length === 0 && (file.through_week ?? 0) > 0) return null
  const games = []
  for (const g of file.games) {
    const p = source === 'student' ? g.p_student : g.p_market
    if (p == null) return null
    games.push({ id: g.game_id, home: g.home, away: g.away, p })
  }
  return {
    played: file.played.map((g) => fromScores(g.home, g.away, g.home_score, g.away_score)),
    games,
    ratings: v.ratings,
    homeAdv: v.home_term,
    sigma: file.shock_sigma,
  }
}
