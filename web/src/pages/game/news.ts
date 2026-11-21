import type { Game } from '../../data/contract'
import { HEADLINE, SHORT } from '../../lib/models'
import { spreadLabel } from '../../lib/format'

/** "Football only HOU −10.2 · news −1.0 (QB questionable; 2 starters ruled out)": the Student's
 * spread before the news and what the news moved it, in points toward the home team's side of
 * the line (ADR 0032). Null without research or when there is nothing to say. */
export function newsLine(g: Game): { football: string; news: string; why: string } | null {
  const n = g.news
  if (!n || n.football_only_spread == null || n.pts == null) return null
  const moved = Math.abs(n.pts) >= 0.05
  const fav = n.football_only_spread >= 0 ? g.home : g.away
  // the news moves the line toward the home team (+) or the away team (−); show it on the favorite's scale
  const onFav = n.football_only_spread >= 0 ? n.pts : -n.pts
  const news = moved ? `${onFav < 0 ? '−' : '+'}${Math.abs(onFav).toFixed(1)}` : 'none'
  const why = n.reasons.map((r) => `${r.team} ${r.label}`).join('; ')
  return {
    football: spreadLabel(n.football_only_spread, g.home, g.away),
    news: moved ? `${news} for ${fav}` : news,
    why,
  }
}

export const NEWS_NAME = SHORT[HEADLINE]
