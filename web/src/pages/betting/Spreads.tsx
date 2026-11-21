import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, Section } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct, signedPct } from '../../lib/format'
import { Lede } from './common'
import { axis, tip } from './facts'

const CHECKS: [keyof BettingMath['targeted'][number]['checks'], string][] = [
  ['both_halves', 'ahead in both halves'],
  ['range_above_zero', '90% range above zero'],
  ['recent', 'ahead 2021–2025'],
  ['neighbour_agrees', 'the next step agrees'],
]

/** The two targeted rules, with the four checks each has to clear, and where games end. */
export function Spreads({ m }: { m: BettingMath }) {
  const margins = m.key_margins.map((k) => ({ margin: k.margin, share: k.share }))
  return (
    <>
      <Section title="Targeted spreads and totals" help="Rules picked in advance for a reason, not searched for. Each must be ahead in both halves of the history, have a 90% range above zero, be ahead in the recent seasons, and have its neighbouring rule agree.">
        <Lede>Two rules were checked against four tests each.</Lede>
        <div className="grid gap-3 lg:grid-cols-2">
          {m.targeted.map((t) => (
            <Card key={t.key}>
              <h3 className="font-semibold">{t.label}</h3>
              <p className="tabular mt-1 text-[14px] text-ink-2">
                {t.n.toLocaleString('en-US')} bets, return {signedPct(t.roi)} (90% range starts at {signedPct(t.roi_lo)}).
              </p>
              <ul className="mt-2 list-none p-0 text-[14px]">
                {CHECKS.map(([k, label]) => (
                  <li key={k} className="flex items-center gap-2">
                    <span aria-hidden="true" className={t.checks[k] ? 'text-[var(--good)]' : 'text-[var(--critical)]'}>{t.checks[k] ? '✓' : '✗'}</span>
                    <span className="sr-only">{t.checks[k] ? 'Yes: ' : 'No: '}</span>
                    {label}
                  </li>
                ))}
              </ul>
              <p className={`mt-2 text-[14px] font-semibold ${t.passes ? 'text-[var(--good)]' : 'text-ink-2'}`}>{t.passes ? 'Passes' : "Doesn't clear the bar"}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Where games end" help="Share of games finishing on each margin. Spreads sit on these numbers, so a half point matters.">
        <Lede>
          Football margins cluster on 3 and 7; when the spread is about 3, the game lands exactly on 3 in {pct(m.lands_on_3, 0)} of games.
        </Lede>
        <div className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 224 }}>
            <BarChart data={margins} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" vertical={false} />
              <XAxis dataKey="margin" {...axis} />
              <YAxis tickFormatter={(v: number) => pct(v, 0)} width={44} {...axis} />
              <Tooltip formatter={(v) => [pct(Number(v), 1), 'Share of games']} labelFormatter={(n) => `Margin of ${n}`} contentStyle={tip} cursor={{ fill: 'var(--surface-2)' }} />
              <Bar dataKey="share" fill="var(--accent)" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Section>
    </>
  )
}
