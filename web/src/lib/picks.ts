/**
 * The visitor's own picks (M26.1): the team they think wins each game, kept in this browser only
 * (localStorage, no accounts). A pick opens until kickoff and is scored only if it was made
 * before kickoff. Stage 2 (the playoff what-if) reads the same picks.
 */
import { useSyncExternalStore } from 'react'
import type { GameRow } from '../data/contract'

export type UserPick = { team: string; at: string }
export type Picks = Record<string, UserPick>

export const PICKS_KEY = 'nfl-picks-v1'
const EMPTY: Picks = Object.freeze({}) as Picks

let cache: Picks | null = null
const listeners = new Set<() => void>()

function clean(v: unknown): Picks {
  if (v == null || typeof v !== 'object' || Array.isArray(v)) return EMPTY
  const out: Picks = {}
  for (const [id, p] of Object.entries(v as Record<string, unknown>)) {
    const x = p as Partial<UserPick> | null
    if (x && typeof x.team === 'string' && typeof x.at === 'string') out[id] = { team: x.team, at: x.at }
  }
  return out
}

function load(): Picks {
  try {
    const raw = localStorage.getItem(PICKS_KEY)
    return raw ? clean(JSON.parse(raw)) : EMPTY
  } catch {
    return EMPTY // storage blocked or a corrupt value: start empty
  }
}

export function getPicks(): Picks {
  if (cache == null) cache = load()
  return cache
}

function save(next: Picks) {
  cache = next
  try {
    localStorage.setItem(PICKS_KEY, JSON.stringify(next))
  } catch {
    // storage blocked: the picks last for this page view
  }
  for (const l of listeners) l()
}

function onStorage(e: StorageEvent) {
  if (e.key !== PICKS_KEY && e.key !== null) return
  cache = load()
  for (const l of listeners) l()
}

function subscribe(l: () => void) {
  listeners.add(l)
  if (listeners.size === 1) window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(l)
    if (listeners.size === 0) window.removeEventListener('storage', onStorage)
  }
}

/** Every pick in this browser; re-renders on a change here or in another tab. */
export function usePicks(): Picks {
  return useSyncExternalStore(subscribe, getPicks, getPicks)
}

/** Can this game still be picked? Until kickoff, and never once it has a result. */
export function pickOpen(g: Pick<GameRow, 'kickoff_utc' | 'result'>, now: number = Date.now()): boolean {
  if (g.result != null) return false
  const t = Date.parse(g.kickoff_utc)
  return Number.isNaN(t) || t > now
}

/** Set (or with `team` null, clear) the pick for one game. Refused once the game has kicked off. */
export function setPick(g: Pick<GameRow, 'game_id' | 'home' | 'away' | 'kickoff_utc' | 'result'>, team: string | null, now: Date = new Date()): boolean {
  if (!pickOpen(g, now.getTime())) return false
  if (team != null && team !== g.home && team !== g.away) return false
  const next = { ...getPicks() }
  if (team == null) delete next[g.game_id]
  else next[g.game_id] = { team, at: now.toISOString() }
  save(next)
  return true
}

/** Clear the open picks among `games` (games already kicked off keep theirs: they're scored). */
export function clearOpenPicks(games: GameRow[], now: number = Date.now()) {
  const cur = getPicks()
  const next = { ...cur }
  for (const g of games) if (pickOpen(g, now)) delete next[g.game_id]
  if (Object.keys(next).length !== Object.keys(cur).length) save(next)
}

/** Season and week from a game id (`2026_10_WAS_NYG`); null for anything else. */
export function weekOf(gameId: string): { season: number; week: number } | null {
  const m = /^(\d{4})_(\d{2})_/.exec(gameId)
  return m ? { season: Number(m[1]), week: Number(m[2]) } : null
}

/** The weeks of `season` that hold at least one pick, ascending. */
export function pickedWeeks(picks: Picks, season: number): number[] {
  const ws = new Set<number>()
  for (const id of Object.keys(picks)) {
    const w = weekOf(id)
    if (w && w.season === season) ws.add(w.week)
  }
  return [...ws].sort((a, b) => a - b)
}

export type Tally = { w: number; l: number }
export type PickRecord = {
  /** Finished games you picked (before kickoff, not a tie). */
  games: number
  you: Tally
  /** The headline approach and the market's favorite, on those same games (where they had a side). */
  model: Tally
  market: Tally
  /** Your picks on games not played yet. */
  pending: number
}

const homeWon = (g: GameRow): boolean | null => {
  const m = g.result?.margin
  return m == null || m === 0 ? null : m > 0
}

/** Your record against the model and the market's favorite, on exactly the games you picked. */
export function scorePicks(picks: Picks, games: GameRow[], model: string): PickRecord {
  const rec: PickRecord = { games: 0, you: { w: 0, l: 0 }, model: { w: 0, l: 0 }, market: { w: 0, l: 0 }, pending: 0 }
  const add = (t: Tally, ok: boolean) => (ok ? t.w++ : t.l++)
  for (const g of games) {
    const p = picks[g.game_id]
    if (!p || (p.team !== g.home && p.team !== g.away)) continue
    if (g.result == null) {
      rec.pending++
      continue
    }
    const won = homeWon(g)
    // a tie counts for nobody; a pick stamped after kickoff isn't a pick
    if (won == null || !(Date.parse(p.at) < Date.parse(g.kickoff_utc))) continue
    rec.games++
    add(rec.you, (p.team === g.home) === won)
    const pm = g.models[model]?.p_home
    if (pm != null && pm !== 0.5) add(rec.model, pm > 0.5 === won)
    const mk = g.market?.p_home
    if (mk != null && mk !== 0.5) add(rec.market, mk > 0.5 === won)
  }
  return rec
}

/** Tests only: forget the in-memory copy so the next read comes from storage. */
export function resetPicksCache() {
  cache = null
}
