/** The week recap's summary tiles, built from the recap alone (pure, unit-tested). */
import type { WeekRecap } from '../../data/contract'
import { dash, pct } from '../../lib/format'
import { APPROACHES, HEADLINE, SHORT } from '../../lib/models'

export type RecapTile = { id: string; label: string; value: string; sub: string; modelId?: string; help?: string }
export type RecapStrip = { tiles: RecapTile[]; caption: string | null }

/** Under 45% in the market is an upset; closer to even is a toss-up (never called an upset). */
const UPSET_BELOW = 0.45
/** Below this a week's tile says even. It describes one week and isn't a ranking, so it's tighter than the tracker's GAP_BAND. */
const NOISE = 0.005

/**
 * The strip's tiles, from the recap, and the caption to print above them. `total` is the week's game
 * count: while the week is still being played the caption says how few games the tiles rest on, so one
 * Thursday game doesn't read like a verdict next to the tracker's full season. Said once, not in each tile.
 */
export function recapTiles(r: WeekRecap, total?: number): RecapStrip {
  const tiles: RecapTile[] = []
  const done = r.games.length
  const caption = total != null && done < total ? `Week ${r.week} so far: ${done} of ${total} games final` : null
  const best = r.models.find((m) => m.model_id === r.best_model)
  tiles.push(
    best
      ? { id: 'best', label: 'Best approach', value: SHORT[best.model_id] ?? best.label, sub: `${best.right} of ${best.n} right, scored ${best.log_loss.toFixed(3)}`, modelId: best.model_id, help: 'Score is log loss, how surprised the forecast was by the results: lower is better.' }
      : { id: 'best', label: 'Best approach', value: dash, sub: 'no finished games' },
  )
  const ap = r.models.filter((m) => (APPROACHES as readonly string[]).includes(m.model_id) && m.vs_market != null)
  if (ap.length > 0) {
    const ahead = ap.filter((m) => m.vs_market! < 0).length
    const gap = ap.reduce((a, m) => a + m.vs_market!, 0) / ap.length
    // decided by the average gap (negative = better)
    const value = Math.abs(gap) < NOISE ? 'Even with the market' : gap < 0 ? 'Scored better' : 'Scored worse'
    const avg = Math.abs(gap) < NOISE ? 'about even' : `${Math.abs(gap).toFixed(3)} ${gap < 0 ? 'better' : 'worse'}`
    tiles.push({ id: 'market', label: 'Forecast score vs market', value, sub: `${ahead} of ${ap.length} ahead, ${avg}`, help: 'Average log loss gap to the market across the approaches; lower is better. Confidence counts, not just picks.' })
  }
  const line = r.models.find((m) => m.model_id === HEADLINE)
  const mk = r.models.find((m) => m.model_id === 'market_baseline')
  const name = SHORT[HEADLINE]
  if (line) tiles.push({ id: 'right', label: 'Picks right', value: `${line.right} of ${line.n}`, sub: `${mk ? `${name}; market ${mk.right} of ${mk.n}` : name}`, modelId: HEADLINE })
  const up = r.upsets[0]
  tiles.push(
    up && up.value < UPSET_BELOW
      ? { id: 'upset', label: 'Biggest upset', value: `${up.away} @ ${up.home}`, sub: `winner was ${pct(up.value)} in the market` }
      : { id: 'upset', label: 'Biggest upset', value: 'None', sub: up ? `lowest winner was ${pct(up.value)} in the market` : done > 0 ? 'every favorite won' : 'no finished games' },
  )
  const lucky = r.luckiest[0]
  if (lucky) tiles.push({ id: 'luck', label: 'Luckiest team', value: lucky.team, sub: `${lucky.luck_net >= 0 ? '+' : '−'}${Math.abs(lucky.luck_net).toFixed(1)} pts of pure luck` })
  return { tiles, caption }
}
