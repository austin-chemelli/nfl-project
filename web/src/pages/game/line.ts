/** Words for the market line's movement (ADR 0024). A spread move > 0 is toward the home team. */
import type { LineMove, LinePoint } from '../../data/contract'
import { spreadLabel } from '../../lib/format'

/** Moves under this many points read as noise on a card. */
export const CARD_MIN_MOVE = 1

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** "Tue" for a timestamp, in Eastern time. */
export function etDay(iso: string): string {
  const d = new Date(iso)
  const et = new Date(d.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  return DAYS[et.getDay()]
}

/** "moved 2.5 toward BAL since Tue", or null when the move is small or unknown. */
export function cardMove(m: LineMove | null | undefined, home: string, away: string): string | null {
  const d = m?.since_first?.spread_home
  if (m == null || d == null || Math.abs(d) < CARD_MIN_MOVE) return null
  return `Line moved ${fmtPts(Math.abs(d))} toward ${d > 0 ? home : away} since ${etDay(m.first_seen)}`
}

export const fmtPts = (v: number) => (Number.isInteger(v) ? `${v}` : v.toFixed(Math.abs(v * 2 - Math.round(v * 2)) < 1e-9 ? 1 : 2))

const firstWith = (pts: LinePoint[], k: 'spread_home' | 'total') => pts.find((p) => p[k] != null)
const lastWith = (pts: LinePoint[], k: 'spread_home' | 'total') => [...pts].reverse().find((p) => p[k] != null)

/** "Spread BAL −2.5 → JAX −10 · total 48.75 → 40.5" from the first and latest points. */
export function pathSentence(pts: LinePoint[], home: string, away: string): string | null {
  const a = firstWith(pts, 'spread_home')
  const b = lastWith(pts, 'spread_home')
  const ta = firstWith(pts, 'total')
  const tb = lastWith(pts, 'total')
  const parts: string[] = []
  if (a && b && a !== b) parts.push(`Spread ${spreadLabel(a.spread_home, home, away)} → ${spreadLabel(b.spread_home, home, away)}`)
  if (ta && tb && ta !== tb) parts.push(`total ${fmtPts(ta.total!)} → ${fmtPts(tb.total!)}`)
  // capitalised whichever part comes first: a total-only move starts the line
  return parts.length ? parts.join(' · ').replace(/^t/, 'T') : null
}

/** "2.5 toward BAL" / "steady" for one window's spread move. */
export function windowWords(d: number | null | undefined, home: string, away: string): string | null {
  if (d == null) return null
  if (Math.abs(d) < 0.25) return 'steady'
  return `${fmtPts(Math.abs(d))} toward ${d > 0 ? home : away}`
}

/** "Mon 7:01 PM" in Eastern time. */
export function etStamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: 'numeric', minute: '2-digit' })
}
