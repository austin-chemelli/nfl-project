/** Pure helpers for the Paper bets tab. */
import type { Tracker } from '../../data/contract'
import { APPROACHES } from '../../lib/models'

type LedgerRow = Tracker['ledger'][number]
type SeasonRow = NonNullable<Tracker['ledger_seasons']>[number]
export type BankrollRow = { season: number; no_edge: number; live: number } & Record<string, number>

/** Return per bet, signed: "−1.2%". */
export function signedPct(v: number, digits = 1): string {
  const s = Math.abs(100 * v).toFixed(digits)
  if (Number(s) === 0) return `${s}%`
  return `${v > 0 ? '+' : '−'}${s}%`
}

/** Units, signed and whole: "+14", "−38", "0". */
export function signedUnits(v: number): string {
  const r = Math.round(Math.abs(v))
  if (r === 0) return '0'
  return `${v > 0 ? '+' : '−'}${r}`
}

/**
 * Running units per line, season by season. `no_edge` is the running cost of the same bets with no
 * edge, averaged over the approaches so the reference line doesn't move as lines are toggled.
 * The first row is the start, one season before the first bets, with everything at zero.
 */
export function bankrollRows(rows: SeasonRow[]): BankrollRow[] {
  const seasons = [...new Set(rows.map((r) => r.season))].sort((a, b) => a - b)
  const ids = [...new Set(rows.map((r) => r.model_id))]
  const approaches = new Set<string>(APPROACHES)
  if (!seasons.length) return []
  const run: Record<string, number> = {}
  let noEdge = 0
  const start = { season: seasons[0] - 1, no_edge: 0, live: 0, ...Object.fromEntries(ids.map((m) => [m, 0])) } as BankrollRow
  const rest = seasons.map((season) => {
    const here = rows.filter((r) => r.season === season)
    for (const m of ids) run[m] = (run[m] ?? 0) + (here.find((r) => r.model_id === m)?.units ?? 0)
    const costs = here.filter((r) => approaches.has(r.model_id)).map((r) => r.no_edge_units)
    if (costs.length) noEdge += costs.reduce((a, b) => a + b, 0) / costs.length
    const live = Math.max(0, ...here.map((r) => r.live_bets))
    const out: BankrollRow = { season, no_edge: Math.round(noEdge * 10) / 10, live } as BankrollRow
    for (const m of ids) (out as Record<string, number>)[m] = Math.round(run[m] * 10) / 10
    return out
  })
  return [start, ...rest]
}

/** Backtest rows that carry a return and its range, best return first. */
export function returnRows(ledger: LedgerRow[]): (LedgerRow & { roi: number; roi_lo: number; roi_hi: number })[] {
  return ledger
    .filter((r): r is LedgerRow & { roi: number; roi_lo: number; roi_hi: number } => r.kind === 'backfill' && r.roi != null && r.roi_lo != null && r.roi_hi != null)
    .sort((a, b) => b.roi - a.roi)
}

/** The average return of the approaches' bets with no edge. */
export function noEdgeReturn(rows: LedgerRow[]): number | null {
  const v = rows.filter((r) => (APPROACHES as readonly string[]).includes(r.model_id) && r.no_edge_roi != null).map((r) => r.no_edge_roi!)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

const COUNT = ['None', 'One', 'Two', 'Three', 'Four']

/** The tab's headline: did any approach make money, and did any do better than paying the cut? */
export function betsVerdict(rows: LedgerRow[], nameOf: (id: string) => string): string | null {
  const lines = returnRows(rows).filter((r) => (APPROACHES as readonly string[]).includes(r.model_id))
  const noEdge = noEdgeReturn(lines)
  if (!lines.length || noEdge == null) return null
  const best = lines[0]
  const name = nameOf(best.model_id)
  const first =
    best.roi < 0
      ? `In the backtest, every approach has lost money. The best, ${name}, is at ${signedPct(best.roi)} a bet.`
      : best.roi_lo > 0
        ? `In the backtest, ${name} is up ${signedPct(best.roi)} a bet, and its whole range clears break-even.`
        : `In the backtest, ${name} is up ${signedPct(best.roi)} a bet, but its range still reaches below break-even.`
  const beat = lines.filter((r) => r.roi > noEdge).length
  const clear = lines.filter((r) => r.roi_lo > noEdge).length
  const count = COUNT[beat] ?? String(beat)
  const rest = beat === 0 ? '' : clear === 0 ? `, none by more than the noise` : `, ${(COUNT[clear] ?? String(clear)).toLowerCase()} clearly`
  const total = (COUNT[lines.length] ?? String(lines.length)).toLowerCase()
  return `${first} Betting with no edge at all costs ${signedPct(noEdge).replace('−', '')} a bet. ${count} of the ${total} did better than that${rest}.`
}

/** A season's live bets for the tooltip: the most any one line has, since lines bet different games. */
export function liveNote(n: number): string {
  return n > 0 ? ` (up to ${n} live ${n === 1 ? 'bet' : 'bets'} a line)` : ''
}

/** A cell's fill: stronger with the size of the swing, in the diverging pair, over the surface. */
export function cellFill(units: number, full = 30): string {
  const share = Math.round(Math.min(Math.abs(units) / full, 1) * 55)
  return `color-mix(in srgb, var(${units >= 0 ? '--div-pos' : '--div-neg'}) ${share}%, transparent)`
}
