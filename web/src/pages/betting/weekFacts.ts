/** Plain helpers for the weekly card and the bet log. */
import type { BettingWeek, CardSide, ClosingGame } from '../../data/contract'
import { dash } from '../../lib/format'
import { decimalOdds, type BetEntry } from '../../lib/betLog'

export const VIEW_NAMES: Record<string, string> = { target: 'Targets', avoid: 'Avoids' }

export type Draft = { game_id: string; side: 'home' | 'away'; price: number; stake: number | null }

/** The price a side's stake is worked out at: the price on offer now, else the price the card needs. */
export function stakePrice(s: Pick<CardSide, 'price' | 'needed'>): number | null {
  return s.price ?? s.needed.american
}

/** Dollars a winning bet pays, from stake and an American price. */
export const toWin = (stake: number, price: number) => stake * (decimalOdds(price) - 1)

const ET = 'America/New_York'
/** "Sun 1:00 PM" in Eastern time. */
export function kickoffShort(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return dash
  const day = d.toLocaleString('en-US', { timeZone: ET, weekday: 'short' })
  const time = d.toLocaleString('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit' })
  return `${day} ${time}`
}

export type GameOption = { game_id: string; away: string; home: string; label: string }

/** The games a bet can be logged on: this week's card plus every game of the season without a final score. */
export function gameOptions(w: BettingWeek): GameOption[] {
  const seen = new Map<string, GameOption>()
  const add = (g: { game_id: string; away: string; home: string; kickoff_utc: string }) => {
    if (!seen.has(g.game_id)) seen.set(g.game_id, { game_id: g.game_id, away: g.away, home: g.home, label: `${g.away} @ ${g.home}, ${kickoffShort(g.kickoff_utc)}` })
  }
  for (const g of w.card.games) add(g)
  for (const g of w.closing) if (g.home_score == null || g.away_score == null) add(g)
  return [...seen.values()]
}

export const closingMap = (w: BettingWeek): Map<string, ClosingGame> => new Map(w.closing.map((g) => [g.game_id, g]))

const signed = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x)}`

/** What a log entry bets on: "HOU to win", "HOU −3.5", "Under 44.5". */
export function describeBet(e: BetEntry, g: { home: string; away: string } | undefined): string {
  const team = g ? (e.side === 'home' ? g.home : g.away) : e.side
  if (e.market === 'ml') return `${team} to win`
  if (e.market === 'spread') return `${team} ${signed(e.line ?? 0)}`
  return `${e.side === 'over' ? 'Over' : 'Under'} ${e.line}`
}

/** "+1.8 pts" of win chance for a moneyline, "+1.5 on the line" for a spread or total. */
export function clvText(e: Pick<BetEntry, 'market'>, v: number | null): string {
  if (v == null) return dash
  const s = `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`
  return e.market === 'ml' ? `${s} pts` : `${s} on the line`
}
