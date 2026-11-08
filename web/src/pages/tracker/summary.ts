/**
 * The tracker's summary strip (ADR 0017): five tiles, each one statement a reader wants first,
 * linking to the tab that explains it. Pure functions over the contract so they are unit-tested.
 *
 * Reuses the section helpers (currentSummary, calibrationVerdict) rather than recomputing, and the
 * same GAP_BAND rule: smaller log-loss gaps are "about the same as the market", never a ranking.
 */
import type { Tracker } from '../../data/contract'
import { APPROACHES, HEADLINE, SHORT } from '../../lib/models'
import { calibrationVerdict, currentSummary, GAP_BAND, type CurrentRow } from './helpers'
import { label } from './names'

export type TabId = 'season' | 'backtest' | 'calibration' | 'bets'

export type TileSpec = {
  id: string
  label: string
  value: string
  sub: string
  tab: TabId
  modelId?: string
}

const NAME = SHORT[HEADLINE]
const n3 = (x: number) => Math.abs(x).toFixed(3)
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/** "0.012 worse than the market" / "about the same as the market" (the noise rule). */
function gapWords(delta: number): string {
  if (Math.abs(delta) < GAP_BAND) return 'about the same as the market'
  return `${n3(delta)} ${delta > 0 ? 'worse' : 'better'} than the market`
}

export function summaryTiles(t: Tracker): TileSpec[] {
  const cur = currentSummary(t.current_season)
  return [vsMarketTile(cur.rows), liveTile(cur), bestTile(cur.rows), calibrationTile(t), betsTile(t)]
}

function vsMarketTile(rows: CurrentRow[]): TileSpec {
  const line = rows.find((r) => r.model_id === HEADLINE)
  if (!line || line.delta == null) return { id: 'season', label: `${NAME} vs the market`, value: '–', sub: 'no graded games yet', tab: 'season', modelId: HEADLINE }
  const value = Math.abs(line.delta) < GAP_BAND ? 'Same as market' : line.delta > 0 ? 'Trails the market' : 'Beats the market'
  return {
    id: 'season', label: `${NAME} vs the market`, value, tab: 'season', modelId: HEADLINE,
    // log loss never alone (format.ts): the gap to the market, and the sample
    sub: Math.abs(line.delta) < GAP_BAND ? `within ${GAP_BAND} over ${plural(line.games, 'game')}` : `${line.delta.toFixed(3).replace('-', '')} ${line.delta > 0 ? 'behind' : 'ahead'}, ${plural(line.games, 'game')}`,
  }
}

function liveTile(cur: ReturnType<typeof currentSummary>): TileSpec {
  if (cur.liveGames === 0) return { id: 'live', label: 'Live games graded', value: 'None yet', sub: 'every number so far is backfill', tab: 'season' }
  return { id: 'live', label: 'Live games graded', value: String(cur.liveGames), sub: `over ${plural(cur.liveWeeks, 'week')}; the rest is backfill`, tab: 'season' }
}

/** Lowest log loss among the four approaches this season, told against the market. */
function bestTile(rows: CurrentRow[]): TileSpec {
  const ps = rows.filter((r) => (APPROACHES as readonly string[]).includes(r.model_id))
  if (ps.length === 0) return { id: 'best', label: 'Best approach so far', value: '–', sub: 'no graded games yet', tab: 'season' }
  const sorted = [...ps].sort((a, b) => a.logLoss - b.logLoss)
  const best = sorted[0]
  const next = sorted[1]
  if (next && next.logLoss - best.logLoss < GAP_BAND)
    return { id: 'best', label: 'Best approach so far', value: 'Too close to call', sub: `${label(best.model_id)} lowest, within noise`, tab: 'season' }
  return {
    id: 'best', label: 'Best approach so far', value: label(best.model_id), tab: 'season', modelId: best.model_id,
    sub: best.delta == null ? `${best.logLoss.toFixed(3)} log loss` : `${best.logLoss.toFixed(3)}, ${gapWords(best.delta)}`,
  }
}

function calibrationTile(t: Tracker): TileSpec {
  const firsts = t.backtest.map((r) => r.first_season)
  const since = firsts.length ? `, since ${Math.min(...firsts)}` : ', all seasons'
  const base = { id: 'calibration', label: `${NAME} calibration${since}`, tab: 'calibration' as const, modelId: HEADLINE }
  const v = calibrationVerdict(t.reliability.filter((r) => r.model_id === HEADLINE), NAME)
  // what it said and the gap are in the Calibration tab's table
  const calls = `60–80% calls won ${Math.round(100 * v.won)}%`
  switch (v.kind) {
    case 'well': return { ...base, value: 'Well calibrated', sub: calls }
    case 'over': return { ...base, value: 'Overconfident', sub: calls }
    case 'under': return { ...base, value: 'Underconfident', sub: calls }
    default: return { ...base, value: 'Too few to judge', sub: 'not enough 60-80% calls' }
  }
}

/** Paper bets for the headline line: this season's live bets once they exist, otherwise the backfill. */
function betsTile(t: Tracker): TileSpec {
  const rows = t.ledger.filter((r) => r.model_id === HEADLINE && r.units != null)
  const row = rows.find((r) => r.kind === 'live') ?? rows[0]
  if (!row) return { id: 'bets', label: 'Paper bets', value: 'None yet', sub: 'no bets recorded', tab: 'bets' }
  const u = row.units!
  const record = `${row.wins}-${row.losses}${row.pushes ? `-${row.pushes}` : ''}`
  if (row.kind === 'live')
    return { id: 'bets', label: 'Paper bets', tab: 'bets', value: `${u >= 0 ? '+' : '−'}${Math.abs(u).toFixed(1)} units`, sub: `${record} on ${plural(row.bets, 'live bet')}` }
  // The backfill row spans every season since 2005: return per bet says more than a huge unit total.
  const roi = row.roi ?? (row.bets > 0 ? u / row.bets : 0)
  const firsts = (t.ledger_seasons ?? []).filter((r) => r.model_id === HEADLINE).map((r) => r.season)
  const since = firsts.length ? Math.min(...firsts) : null
  return {
    id: 'bets', label: 'Paper bets, backtest', tab: 'bets',
    value: `${roi >= 0 ? '+' : '−'}${(100 * Math.abs(roi)).toFixed(1)}% a bet`,
    modelId: HEADLINE,
    sub: `${NAME}: ${row.bets.toLocaleString('en-US')} bets${since ? ` since ${since}` : ''}`, // the record and "live bets start with the locks" are in the tab
  }
}
