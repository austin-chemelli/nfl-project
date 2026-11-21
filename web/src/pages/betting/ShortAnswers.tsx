import { Card } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct, signedPct } from '../../lib/format'
import { chance } from './facts'

function Answer({ q, a, children }: { q: string; a: string; children?: string }) {
  return (
    <Card>
      <h3 className="font-semibold">{q}</h3>
      <p className="mt-1 font-bold text-ink">{a}</p>
      {children && <p className="tabular mt-1 text-[14px] text-ink-2">{children}</p>}
    </Card>
  )
}

/** The questions a bettor asks: a one-line answer and one number each, from the study's own figures. */
export function ShortAnswers({ m }: { m: BettingMath }) {
  const r = m.rules
  const ranked = r.ranked_walk_forward ?? r.ranked
  const kellyFull = m.staking.find((s) => s.strategy === 'kelly_full' && s.bets_per_week === 6)
  const pts = (x: number) => Math.round(x * 100)
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Answer q="Which bets are worth making?" a={`The week's five best by history; still about the cut out of sample (${signedPct(ranked?.roi)}).`}>
        {`Underdogs at +120 to +185 did best: ${signedPct(r.lean_dog.roi)} on ${r.lean_dog.n.toLocaleString('en-US')} bets since 2006, ${signedPct(r.lean_dog.roi_2021_2025)} in 2021–2025.`}
      </Answer>

      <Answer q="What should I stay away from?" a="Middle favorites, long shots, and big disagreements with the market.">
        {`−120 to −185: ${signedPct(r.mid_fav.roi)}. +185 or longer: ${signedPct(r.long.roi)}. Student ${pts(r.limits.lean_max)}+ points above the market: ${signedPct(r.big_gap.roi)}.`}
      </Answer>

      <Answer q="Why not bet the Student's pick in every game?" a="It still loses, because the price already counts the pick.">
        {`Won ${pct(r.model_pick.win_rate)} of the time, returned ${signedPct(r.model_pick.roi)} on ${r.model_pick.n.toLocaleString('en-US')} bets.`}
      </Answer>

      <Answer q="One bet at a time, or parlays?" a="Singles. Each leg multiplies the house's cut.">
        {m.parlays.map((p) => `${p.legs} ${p.legs === 1 ? 'leg' : 'legs'} ${signedPct(p.roi)}`).join(' · ')}
      </Answer>

      <Answer q="How much should I stake?" a="1% of your bankroll a bet.">
        {kellyFull ? `Kelly fed the model's own confidence lost half the bankroll in ${chance(kellyFull.p_lose_half)} of seasons.` : undefined}
      </Answer>
    </div>
  )
}
