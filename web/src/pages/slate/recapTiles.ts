/** The week recap's summary tiles, built from the recap alone (pure, unit-tested). */
import type { WeekRecap } from '../../data/contract'
import { dash, pct } from '../../lib/format'
import { APPROACHES, HEADLINE, SHORT } from '../../lib/models'

export type RecapTile = { id: string; label: string; value: string; sub: string; modelId?: string }

/** Under 45% in the market is an upset; closer to even is a toss-up (never called an upset). */
const UPSET_BELOW = 0.45
/** Log-loss gaps under this are noise at a week's sample size (the tracker uses the same rule). */
const NOISE = 0.005

/** The strip's tiles, from the recap alone. */
export function recapTiles(r: WeekRecap): RecapTile[] {
  const tiles: RecapTile[] = []
  const best = r.models.find((m) => m.model_id === r.best_model)
  tiles.push(
    best
      ? { id: 'best', label: 'Best approach', value: SHORT[best.model_id] ?? best.label, sub: `${best.right} of ${best.n} right, log loss ${best.log_loss.toFixed(3)}`, modelId: best.model_id }
      : { id: 'best', label: 'Best approach', value: dash, sub: 'no finished games' },
  )
  const ap = r.models.filter((m) => (APPROACHES as readonly string[]).includes(m.model_id) && m.vs_market != null)
  if (ap.length > 0) {
    const ahead = ap.filter((m) => m.vs_market! < 0).length
    const gap = ap.reduce((a, m) => a + m.vs_market!, 0) / ap.length
    // decided by the average gap (negative = better), with the tracker's noise rule
    const value = Math.abs(gap) < NOISE ? 'Even with the market' : gap < 0 ? 'Beat the market' : 'Trailed the market'
    const avg = Math.abs(gap) < NOISE ? 'about even on average' : `${Math.abs(gap).toFixed(3)} log loss ${gap < 0 ? 'better' : 'worse'} on average`
    tiles.push({ id: 'market', label: 'vs the market', value, sub: `${ahead} of ${ap.length} ahead; ${avg}` })
  }
  const line = r.models.find((m) => m.model_id === HEADLINE)
  const mk = r.models.find((m) => m.model_id === 'market_baseline')
  const name = SHORT[HEADLINE]
  if (line) tiles.push({ id: 'right', label: 'Picks right', value: `${line.right} of ${line.n}`, sub: mk ? `${name}; market ${mk.right} of ${mk.n}` : name, modelId: HEADLINE })
  const up = r.upsets[0]
  tiles.push(
    up && up.value < UPSET_BELOW
      ? { id: 'upset', label: 'Biggest upset', value: `${up.away} @ ${up.home}`, sub: `winner was ${pct(up.value)} in the market` }
      : { id: 'upset', label: 'Biggest upset', value: 'None', sub: up ? `lowest winner was ${pct(up.value)} in the market` : 'no finished games' },
  )
  const lucky = r.luckiest[0]
  if (lucky) tiles.push({ id: 'luck', label: 'Luckiest team', value: lucky.team, sub: `${lucky.luck_net >= 0 ? '+' : '−'}${Math.abs(lucky.luck_net).toFixed(1)} pts of pure luck` })
  return tiles
}
