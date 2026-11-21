import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Section } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct, signedPct } from '../../lib/format'
import { RulesTable } from './RulesTable'
import { Lede } from './common'
import { axis, tip } from './facts'

/** What the models add on top of the price. */
export function Models({ m }: { m: BettingMath }) {
  const wf = m.walk_forward
  const seasons = wf.seasons.filter((s) => s.roi != null).map((s) => ({ season: s.season, roi: s.roi as number, bets: s.bets }))
  return (
    <>
      <Section title="How much of our model to keep" help="Each season, history is asked how far to move from the market's price toward our model's. 0% means trust the market fully; 100% means trust the model fully.">
        <Lede>How much of our model&apos;s disagreement history says to keep.</Lede>
        <div className="h-60 w-full">
          <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 240 }}>
            <LineChart data={m.blend} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
              <XAxis dataKey="season" type="number" domain={['dataMin', 'dataMax']} allowDecimals={false} {...axis} />
              <YAxis tickFormatter={(v: number) => pct(v, 0)} width={44} domain={[0, 'auto']} {...axis} />
              <Tooltip formatter={(v) => [pct(Number(v), 0), 'Kept']} labelFormatter={(s) => `Season ${s}`} contentStyle={tip} />
              <Line dataKey="w" name="w" type="linear" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Section>

      <Section title="The search for a rule that works" help="Try enough rules and some will look good by luck. The fair test picks each season's rule using only earlier seasons, then bets it.">
        <Lede>
          We tried {wf.rules_tried} rules. Choosing each season&apos;s rule from earlier seasons only, and betting it, returned {signedPct(wf.walk_forward_roi)} over {wf.walk_forward_bets.toLocaleString('en-US')} bets.
        </Lede>
        <ul className="mb-3 list-none p-0 text-[14px] text-ink-2">
          <li className="tabular">The best rule in hindsight returned {signedPct(wf.best_in_hindsight_roi)}; the median rule {signedPct(wf.median_rule_roi)}.</li>
          <li className="tabular">{wf.positive_both_halves} of {wf.rules_tried} rules were ahead in both halves of the history.</li>
        </ul>
        <div className="h-60 w-full">
          <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 240 }}>
            <BarChart data={seasons} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" vertical={false} />
              <ReferenceLine y={0} stroke="var(--text-muted)" strokeWidth={1.5} />
              <XAxis dataKey="season" tickFormatter={(s: number) => String(s).slice(2)} {...axis} />
              <YAxis tickFormatter={(v: number) => signedPct(v, 0)} width={52} {...axis} />
              <Tooltip formatter={(v) => [signedPct(Number(v)), 'Return']} labelFormatter={(s) => `Season ${s}`} contentStyle={tip} cursor={{ fill: 'var(--surface-2)' }} />
              <Bar dataKey="roi" isAnimationActive={false}>
                {seasons.map((s) => (
                  <Cell key={s.season} fill={s.roi >= 0 ? 'var(--good)' : 'var(--critical)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Section>

      <Section title="Where the Student is worth following" help="The card's groups by how far the Student is from the market, and what each returned in history.">
        <Lede>
          The Student&apos;s whole gap to the market comes from games where it disagrees by {Math.round(m.rules.limits.lean_max * 100)} points or more; within that, it is as good as the market. That is why the card backs small leans and stays away from big ones.
        </Lede>
        <RulesTable rules={m.rules} />
      </Section>
    </>
  )
}
