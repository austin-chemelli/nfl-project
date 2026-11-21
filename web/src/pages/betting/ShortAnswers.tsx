import type { ReactNode } from 'react'
import { Card } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct, signedPct } from '../../lib/format'
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

/** The questions a bettor asks, each answered from the study's own numbers. */
export function ShortAnswers({ m }: { m: BettingMath }) {
  const r = m.rules
  const four = m.parlays.find((p) => p.legs === 4)
  const stake = (id: string) => m.staking.find((s) => s.strategy === id && s.bets_per_week === 6)
  const shrunk = stake('kelly_shrunk')
  const kellyFull = stake('kelly_full')
  const lim = r.limits
  const pts = (x: number) => Math.round(x * 100)
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Answer q="Which bets are worth making?" a="Small leans, and underdogs from +120 to +185 most of all.">
        <p className="tabular">
          Where the Student likes a team {pts(lim.lean_min)} to {pts(lim.lean_max)} points of win chance more than the market, bets returned {signedPct(r.target.roi)} on {r.target.n.toLocaleString('en-US')} bets since 2006. Underdogs at +120 to +185 did best: {signedPct(r.lean_dog.roi)} on {r.lean_dog.n.toLocaleString('en-US')} bets.
        </p>
        <p className="tabular">Even that spot returned {signedPct(r.lean_dog.roi_2021_2025)} in 2021–2025: a small, fading edge, not a sure thing.</p>
      </Answer>

      <Answer q="What should I stay away from?" a="Middle favorites, long shots, and big disagreements with the market.">
        <p className="tabular">
          Favorites from −120 to −185 returned {signedPct(r.mid_fav.roi)}; anything at +185 or longer returned {signedPct(r.long.roi)}. When the Student was {pts(lim.lean_max)}+ points above the market it returned {signedPct(r.big_gap.roi)}, and {signedPct(r.big_gap.roi_second)} since 2016.
        </p>
      </Answer>

      <Answer q="Why not bet the Student's pick in every game?" a="It still loses, because the price already counts the pick.">
        <p className="tabular">
          Betting the Student&apos;s side in every game won {pct(r.model_pick.win_rate)} of the time and returned {signedPct(r.model_pick.roi)} on {r.model_pick.n.toLocaleString('en-US')} bets.
        </p>
      </Answer>

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

      <Answer q="How much should I stake?" a="1% of your bankroll a bet.">
        <p>
          Kelly sizes a bet by the edge, so it is only as good as the edge you feed it.{' '}
          {shrunk && <span className="tabular">Fed the honest chance (the market plus the small share of our model history says to keep), it staked about {shrunk.avg_stake_pct?.toFixed(1)}% a bet and still ended the typical season at {chance(shrunk.median_end)} of the bankroll. </span>}
          {kellyFull && <span className="tabular">Kelly fed the model&apos;s own confidence lost half the bankroll in {chance(kellyFull.p_lose_half)} of seasons (6 bets a week).</span>}
        </p>
      </Answer>
    </div>
  )
}
