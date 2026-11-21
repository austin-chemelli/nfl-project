/**
 * The visitor's private bet log (ADR 0033): the bets they actually placed, kept in this browser only
 * (localStorage, no accounts, nothing sent anywhere). Graded against the closing map in
 * site/betting_week.json (final score and our last pre-kickoff consensus per game).
 */
import type { ClosingGame } from '../data/contract'
import { createStore } from './browserStore'

export type Market = 'ml' | 'spread' | 'total'
export type Side = 'home' | 'away' | 'over' | 'under'
export type BetEntry = {
  id: string
  game_id: string
  market: Market
  side: Side
  /** The spread point in book convention (home −3.5), or the total; null for a moneyline. */
  line: number | null
  /** American price paid. */
  price: number
  /** Dollars. */
  stake: number
  /** Dollars (an exchange's fee on the trade); 0 when none. */
  fee: number
  venue: string
  /** ISO timestamp. */
  placed_at: string
  note?: string
}
export type Result = 'open' | 'win' | 'loss' | 'push'

export const BETS_KEY = 'nfl-bets-v1'
export const VENUES = ['Underdog', 'Kalshi', 'Polymarket US', 'DraftKings Predictions', 'FanDuel Predicts', 'Other']

// ------------------------------------------------------------------------------------ prices

/** Decimal odds of an American price: −245 pays 1.408 per 1 staked, +130 pays 2.30. */
export const decimalOdds = (price: number): number => (price > 0 ? 1 + price / 100 : 1 + 100 / Math.abs(price))

/** The chance an American price implies, vig included. */
export const impliedChance = (price: number): number => 1 / decimalOdds(price)

/** An exchange contract price in cents (the price is the implied chance) as an American price; null outside 1 to 99. */
export function americanFromCents(cents: number): number | null {
  if (!Number.isFinite(cents) || cents <= 0 || cents >= 100) return null
  const dec = 100 / cents
  return Math.round(dec >= 2 ? (dec - 1) * 100 : -100 / (dec - 1))
}

/** An American price must be at least 100 either way. */
export const validPrice = (price: number): boolean => Number.isFinite(price) && price !== 0 && Math.abs(price) >= 100

// ----------------------------------------------------------------------------------- grading

/** Win, loss or push against the final score; open while either score is missing. */
export function gradeBet(e: Pick<BetEntry, 'market' | 'side' | 'line'>, g: Pick<ClosingGame, 'home_score' | 'away_score'> | undefined): Result {
  if (!g || g.home_score == null || g.away_score == null) return 'open'
  const margin = g.home_score - g.away_score
  const sideMargin = e.side === 'home' ? margin : -margin
  let v: number
  if (e.market === 'ml') {
    if (e.side !== 'home' && e.side !== 'away') return 'open'
    v = sideMargin
  } else if (e.market === 'spread') {
    if ((e.side !== 'home' && e.side !== 'away') || e.line == null) return 'open'
    v = sideMargin + e.line
  } else {
    if ((e.side !== 'over' && e.side !== 'under') || e.line == null) return 'open'
    const pts = g.home_score + g.away_score
    v = e.side === 'over' ? pts - e.line : e.line - pts
  }
  return v > 0 ? 'win' : v < 0 ? 'loss' : 'push'
}

/** Dollars won or lost, fee included; null while the bet is open. */
export function betProfit(e: Pick<BetEntry, 'price' | 'stake' | 'fee'>, result: Result): number | null {
  if (result === 'open') return null
  if (result === 'win') return e.stake * (decimalOdds(e.price) - 1) - e.fee
  if (result === 'loss') return -e.stake - e.fee
  return -e.fee
}

/**
 * Closing-line value: how much better than the close the bet was. Moneyline: the closing fair chance of
 * the side minus the chance the price paid implies, in points of chance. Spread and total: points of line.
 * Null when there is no closing line.
 */
export function betClv(e: Pick<BetEntry, 'market' | 'side' | 'line' | 'price'>, g: Pick<ClosingGame, 'close'> | undefined): number | null {
  const c = g?.close
  if (!c) return null
  if (e.market === 'ml') {
    if (c.p_home == null) return null
    const fair = e.side === 'home' ? c.p_home : 1 - c.p_home
    return 100 * (fair - impliedChance(e.price))
  }
  if (e.line == null) return null
  if (e.market === 'spread') {
    if (c.spread_home == null) return null
    const closing = e.side === 'home' ? -c.spread_home : c.spread_home
    return e.line - closing
  }
  if (c.total == null) return null
  return e.side === 'under' ? e.line - c.total : c.total - e.line
}

export type LogSummary = {
  bets: number
  open: number
  wins: number
  losses: number
  pushes: number
  staked: number
  profit: number
  roi: number | null
  /** Mean closing-line value of the moneyline bets that have one, in points of chance. */
  avgClvMl: number | null
}

export function summarize(entries: BetEntry[], games: Map<string, ClosingGame>): LogSummary {
  const s: LogSummary = { bets: entries.length, open: 0, wins: 0, losses: 0, pushes: 0, staked: 0, profit: 0, roi: null, avgClvMl: null }
  const clvs: number[] = []
  for (const e of entries) {
    const g = games.get(e.game_id)
    const r = gradeBet(e, g)
    if (e.market === 'ml') {
      const c = betClv(e, g)
      if (c != null) clvs.push(c)
    }
    const p = betProfit(e, r)
    if (p == null) {
      s.open++
      continue
    }
    s.staked += e.stake
    s.profit += p
    if (r === 'win') s.wins++
    else if (r === 'loss') s.losses++
    else s.pushes++
  }
  s.roi = s.staked > 0 ? s.profit / s.staked : null
  s.avgClvMl = clvs.length ? clvs.reduce((a, b) => a + b, 0) / clvs.length : null
  return s
}

// ------------------------------------------------------------------------------------ entries

const MARKETS: Market[] = ['ml', 'spread', 'total']
const sideOk = (m: Market, s: unknown) => (m === 'total' ? s === 'over' || s === 'under' : s === 'home' || s === 'away')

/** A well-formed entry from anything, or null. Missing fee, venue and line get their defaults. */
export function parseEntry(x: unknown): BetEntry | null {
  if (x == null || typeof x !== 'object' || Array.isArray(x)) return null
  const o = x as Record<string, unknown>
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  if (typeof o.id !== 'string' || !o.id || typeof o.game_id !== 'string' || !o.game_id) return null
  if (!MARKETS.includes(o.market as Market) || !sideOk(o.market as Market, o.side)) return null
  const price = num(o.price)
  const stake = num(o.stake)
  if (price == null || !validPrice(price) || stake == null || stake <= 0) return null
  const fee = o.fee == null ? 0 : num(o.fee)
  if (fee == null || fee < 0) return null
  const line = o.line == null ? null : num(o.line)
  if (o.line != null && line == null) return null
  if (o.market !== 'ml' && line == null) return null
  if (typeof o.placed_at !== 'string' || Number.isNaN(Date.parse(o.placed_at))) return null
  const e: BetEntry = {
    id: o.id,
    game_id: o.game_id,
    market: o.market as Market,
    side: o.side as Side,
    line: o.market === 'ml' ? null : line,
    price,
    stake,
    fee,
    venue: typeof o.venue === 'string' ? o.venue : '',
    placed_at: o.placed_at,
  }
  if (typeof o.note === 'string' && o.note) e.note = o.note
  return e
}

const store = createStore<BetEntry[]>(BETS_KEY, [], (raw) => (Array.isArray(raw) ? raw.flatMap((x) => parseEntry(x) ?? []) : []))

export const useBets = store.use
export const getBets = store.get
export const resetBetsCache = store.reset

export function newBetId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/** Timestamps for new entries and export file names. */
export const nowIso = (): string => new Date().toISOString()
export const exportName = (ext: string): string => `nfl-bets-${nowIso().slice(0, 10)}.${ext}`

export function addBet(e: BetEntry) {
  store.set([...getBets(), e])
}

export function deleteBet(id: string) {
  store.set(getBets().filter((e) => e.id !== id))
}

/** Merge exported JSON into `current` by id (an imported row replaces the same id); malformed rows are skipped and counted. */
export function mergeImport(current: BetEntry[], text: string): { next: BetEntry[]; added: number; skipped: number } {
  let rows: unknown
  try {
    rows = JSON.parse(text)
  } catch {
    return { next: current, added: 0, skipped: 0 }
  }
  if (rows != null && typeof rows === 'object' && !Array.isArray(rows) && Array.isArray((rows as { bets?: unknown }).bets)) rows = (rows as { bets: unknown[] }).bets
  if (!Array.isArray(rows)) return { next: current, added: 0, skipped: 0 }
  const byId = new Map(current.map((e) => [e.id, e]))
  let added = 0
  let skipped = 0
  for (const r of rows) {
    const e = parseEntry(r)
    if (!e) {
      skipped++
      continue
    }
    if (!byId.has(e.id)) added++
    byId.set(e.id, e)
  }
  return { next: [...byId.values()], added, skipped }
}

export function importBets(text: string): { added: number; skipped: number } {
  const current = getBets()
  const { next, added, skipped } = mergeImport(current, text)
  if (next !== current) store.set(next)
  return { added, skipped }
}

const CSV_COLS = ['id', 'game_id', 'market', 'side', 'line', 'price', 'stake', 'fee', 'venue', 'placed_at', 'note'] as const

export function toCsv(entries: BetEntry[]): string {
  const cell = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [CSV_COLS.join(','), ...entries.map((e) => CSV_COLS.map((c) => cell(e[c])).join(','))].join('\n') + '\n'
}

export const toJson = (entries: BetEntry[]): string => JSON.stringify(entries, null, 2)

/** Hand the visitor a file: a Blob behind an object URL. */
export function downloadFile(name: string, mime: string, body: string) {
  const url = URL.createObjectURL(new Blob([body], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.parentNode?.removeChild(a)
  URL.revokeObjectURL(url)
}
