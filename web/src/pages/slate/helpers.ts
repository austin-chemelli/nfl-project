/** Pure helpers for the Slate page (port of nfl.ui.slate_helpers). */
import type { GameRow, Meta } from '../../data/contract'
import { APPROACHES } from '../../lib/models'
import { pct } from '../../lib/format'

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

export function gameStatus(game: GameRow): { status: string; lockTs: string | null } {
  const m = game.models.ensemble ?? Object.values(game.models)[0]
  return m ? { status: m.status, lockTs: m.lock_ts } : { status: 'preview', lockTs: null }
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
