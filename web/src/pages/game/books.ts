/** Words for where the sportsbooks disagree (ADR 0024, M20.13). Spreads: + = home favored. */
import type { BookLine, Books, Game } from '../../data/contract'
import { spreadLabel } from '../../lib/format'
import { fmtPts } from './line'

/** Odds API keys to the names people know; an unknown key shows as itself. */
const BOOK_NAMES: Record<string, string> = {
  draftkings: 'DraftKings', fanduel: 'FanDuel', betmgm: 'BetMGM', betrivers: 'BetRivers', williamhill_us: 'Caesars',
  espnbet: 'ESPN BET', fanatics: 'Fanatics', ballybet: 'Bally Bet', hardrockbet: 'Hard Rock Bet', betparx: 'betPARX',
  betonlineag: 'BetOnline', bovada: 'Bovada', betus: 'BetUS', lowvig: 'LowVig', mybookieag: 'MyBookie', pinnacle: 'Pinnacle',
}
export const bookName = (key: string) => BOOK_NAMES[key] ?? key

/** Something to show: three or more books quoting a spread or a total. */
export const hasBooks = (g: Game) => g.books != null && (g.books.spread != null || g.books.total != null)
/** The books disagree enough to flag (a gap, or a key number between them). */
export const disagrees = (b: Books | null | undefined) => b != null && b.flags.length > 0

/** "DraftKings" or "DraftKings and FanDuel" or "DraftKings, FanDuel and 2 more". */
export function names(rows: BookLine[]): string {
  const n = rows.map((r) => bookName(r.book))
  if (n.length <= 1) return n[0] ?? ''
  if (n.length === 2) return `${n[0]} and ${n[1]}`
  return `${n[0]}, ${n[1]} and ${n.length - 2} more`
}

const at = (b: Books, k: 'spread_home' | 'total', v: number) => b.books.filter((r) => r[k] === v)

/** The one-paragraph read: what the books disagree on, or that they agree. */
export function booksSentence(b: Books, home: string, away: string): string {
  const parts: string[] = []
  const s = b.spread
  if (s) {
    const lo = `${spreadLabel(s.lo, home, away)} at ${names(at(b, 'spread_home', s.lo))}`
    const hi = `${spreadLabel(s.hi, home, away)} at ${names(at(b, 'spread_home', s.hi))}`
    if (b.key === 0) parts.push(`The books don't agree on the favorite: ${lo}, ${hi}.`)
    else if (b.key != null) parts.push(`The books sit on both sides of ${Math.abs(b.key)}, a key number: ${lo}, ${hi}.`)
    else if (b.flags.includes('spread_gap')) parts.push(`The books are ${fmtPts(s.gap)} points apart on the spread: ${lo}, ${hi}.`)
    else if (s.gap === 0) parts.push(`Every book has ${spreadLabel(s.lo, home, away)}.`)
    else parts.push(`The books agree on the spread within ${fmtPts(s.gap)} of a point: ${spreadLabel(s.lo, home, away)} to ${spreadLabel(s.hi, home, away)}.`)
  }
  const t = b.total
  if (t) {
    if (b.flags.includes('total_gap')) parts.push(`On the total they're ${fmtPts(t.gap)} points apart: ${fmtPts(t.lo)} at ${names(at(b, 'total', t.lo))}, ${fmtPts(t.hi)} at ${names(at(b, 'total', t.hi))}.`)
    else if (t.gap === 0) parts.push(`Every book has the total at ${fmtPts(t.lo)}.`)
    else parts.push(`The total runs ${fmtPts(t.lo)} to ${fmtPts(t.hi)}.`)
  }
  return parts.join(' ')
}

/** "JAX −9.5 to −8.5": the second end drops the team when both ends favor the same one, biggest number first. */
function range(lo: number, hi: number, home: string, away: string): string {
  const same = Math.sign(lo) === Math.sign(hi) && lo !== 0
  const [x, y] = same && Math.abs(hi) > Math.abs(lo) ? [hi, lo] : [lo, hi]
  const a = spreadLabel(x, home, away)
  const b = spreadLabel(y, home, away)
  const team = a.split(' ')[0]
  return b.startsWith(`${team} `) ? `${a} to ${b.slice(team.length + 1)}` : `${a} to ${b}`
}

/** "Spread JAX −9.5 to −8.5 · total 40 to 40.5": the books' range when they agree. */
export function booksRange(b: Books, home: string, away: string): string {
  const parts: string[] = []
  const s = b.spread
  if (s) parts.push(`Spread ${s.gap === 0 ? spreadLabel(s.lo, home, away) : range(s.lo, s.hi, home, away)}`)
  const t = b.total
  if (t) parts.push(`${s ? 'total' : 'Total'} ${t.gap === 0 ? fmtPts(t.lo) : `${fmtPts(t.lo)} to ${fmtPts(t.hi)}`}`)
  return parts.join(' · ')
}

/** American odds as printed: "+100", "−110". */
export const price = (p: number | null) => (p == null ? '' : p > 0 ? `+${p}` : `−${Math.abs(p)}`)
