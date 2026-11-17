/** Previous / next game within a week, in the slate's default (kickoff) order. Pure, so it is tested on its own. */
import type { GameRow } from '../../data/contract'
import { byKickoff } from '../slate/helpers'

export type NavGame = { game_id: string; away: string; home: string }

/** "2026_10_DAL_PHI" -> season 2026, week 10; null when the id isn't a game id. */
export function weekOf(id: string | undefined): { season: number; week: number } | null {
  const m = id?.match(/^(\d{4})_(\d{2})_[A-Z]+_[A-Z]+$/)
  return m ? { season: Number(m[1]), week: Number(m[2]) } : null
}

/** The games either side of `id` in the slate's order, and its place in the week. No wrap-around. */
export function slateNeighbours(games: GameRow[], id: string): { prev: NavGame | null; next: NavGame | null; index: number; total: number } {
  const order = byKickoff(games)
  const i = order.findIndex((g) => g.game_id === id)
  if (i < 0) return { prev: null, next: null, index: -1, total: order.length }
  const pick = (g: GameRow | undefined): NavGame | null => (g ? { game_id: g.game_id, away: g.away, home: g.home } : null)
  return { prev: pick(order[i - 1]), next: pick(order[i + 1]), index: i, total: order.length }
}

/** The link to another game that keeps the current tab; the game page falls back to its default tab when it has no such tab. */
export function gameHref(id: string, tab: string | null): string {
  return tab ? `/game/${id}?tab=${encodeURIComponent(tab)}` : `/game/${id}`
}

/** Whether a left/right arrow press should step games: never while typing, in a widget that owns the arrows, or with a modifier. */
export function arrowStepsGames(e: Pick<KeyboardEvent, 'key' | 'altKey' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'defaultPrevented' | 'target'>): boolean {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return false
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return false
  const t = e.target
  if (!(t instanceof Element)) return true
  if (t instanceof HTMLElement && t.isContentEditable) return false
  return !t.closest('input, textarea, select, [contenteditable], [role="tablist"], [role="tab"], [role="slider"], [role="radiogroup"], [role="radio"], [role="listbox"], [role="menu"], [role="grid"], [role="spinbutton"]')
}
