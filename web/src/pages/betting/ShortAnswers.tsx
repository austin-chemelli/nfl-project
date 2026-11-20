import type { ReactNode } from 'react'
import { Card } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { american, pct, signedPct } from '../../lib/format'
import { chance } from './facts'

function Answer({ q, a, children }: { q: string; a: string; children: ReactNode }) {
  return (
    <Card>
      <h3 className="font-semibold">{q}</h3>
      <p className="mt-1 font-bold text-ink">{a}</p>
      <div className="mt-2 flex flex-col gap-2 text-[14px] text-ink-2">{children}</div>
    </Card>
  )
}

const wins = (price: number) => (Math.abs(price) / 100).toFixed(1).replace(/\.0$/, '')

/** Five questions a bettor asks, each answered from the study's own numbers. */
export function ShortAnswers({ m }: { m: BettingMath }) {
  const band = (id: string) => m.bands.find((b) => b.band === id)
  const heavy = band('heavy_fav')
  const big = band('big_fav')
  const coin = band('coin')
  const coinPick = m.pick_winners.find((b) => b.band === 'coin')
  const four = m.parlays.find((p) => p.legs === 4)
  const stake = (id: string) => m.staking.find((s) => s.strategy === id && s.bets_per_week === 6)
  const shrunk = stake('kelly_shrunk')
  const kellyFull = stake('kelly_full')
  const w = m.blend.at(-1)?.w
  const sh = m.shopping
  const rangeHasZero = coinPick?.roi_lo != null && coinPick.roi_hi != null && coinPick.roi_lo < 0 && coinPick.roi_hi > 0
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Answer q="One bet at a time, or parlays?" a="Singles. Each leg multiplies the house's cut.">
        <p>
          Return by number of legs:{' '}
          <span className="tabular">{m.parlays.map((p) => `${p.legs} ${p.legs === 1 ? 'leg' : 'legs'} ${signedPct(p.roi)}`).join(' · ')}.
          </span>
        </p>
        {four && (
          <p>
            Parlays hit about as often as their prices implied ({pct(four.hit_rate, 1)} against {pct(four.market_hit_rate, 1)} at 4 legs), so the problem is the cut multiplying, not luck.
          </p>
        )}
      </Answer>

      <Answer q="Heavy favorites: a sure thing at a tiny payout?" a="The least costly bets there are, and still a small loss.">
        {heavy && big && (
          <p>
            <span className="tabular">
              {heavy.label}s ({heavy.prices.replace(/-(\d)/g, '−$1')}) won {pct(heavy.win_rate)} and returned {signedPct(heavy.roi)}; {big.label.toLowerCase()}s won {pct(big.win_rate)} and returned {signedPct(big.roi)}.
            </span>
          </p>
        )}
        {heavy?.median_price != null && (
          <p>
            The payout is small, so one loss at {american(heavy.median_price)} erases about {wins(heavy.median_price)} wins.
          </p>
        )}
      </Answer>

      <Answer q="Coin flips?" a="You pay the cut and nothing else.">
        {coin && (
          <p>
            <span className="tabular">
              Near even money ({coin.prices.replace(/-(\d)/g, '−$1')}) a side wins {pct(coin.win_rate)} of the time and returns {signedPct(coin.roi)}.
            </span>
          </p>
        )}
        {coinPick && (
          <p>
            <span className="tabular">
              The model&apos;s pick in coin flips won {pct(coinPick.win_rate)} and returned {signedPct(coinPick.roi)} (90% range {signedPct(coinPick.roi_lo)} to {signedPct(coinPick.roi_hi)})
            </span>
            {rangeHasZero ? ': the range includes zero, so it can’t be told from a coin.' : '.'}
          </p>
        )}
      </Answer>

      <Answer q="How much should I stake?" a="1% of your bankroll a bet.">
        <p>
          Kelly sizes a bet by the edge. With no proven edge it says bet nothing:{' '}
          {shrunk && <span className="tabular">on the chance shrunk toward the market it averaged {shrunk.avg_stake_pct?.toFixed(2)}% of the bankroll a bet. </span>}
          {kellyFull && <span className="tabular">Kelly fed the model&apos;s own confidence lost half the bankroll in {chance(kellyFull.p_lose_half)} of seasons (6 bets a week).</span>}
        </p>
      </Answer>

      <Answer q="Why does the price matter more than the pick?" a="Shopping for the best price is the one cost you control.">
        <p>
          <span className="tabular">
            Across {sh.prices.toLocaleString('en-US')} prices from licensed books, the best price returned {signedPct(sh.ev_best)} on average, the median {signedPct(sh.ev_median)}, the worst {signedPct(sh.ev_worst)}; the best price beat the fair price {chance(sh.best_beats_fair_share)} of the time.
          </span>
        </p>
        {w != null && <p>History says keep about {pct(w, 0)} of where our model differs from the market.</p>}
      </Answer>
    </div>
  )
}
