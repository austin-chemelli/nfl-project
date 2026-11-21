import { useState } from 'react'
import { Section, Segmented, TableScroll, td, th } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct } from '../../lib/format'
import { Lede } from './common'
import { chance } from './facts'

/** What each staking rule did over replayed 18-week seasons. */
export function Stakes({ m }: { m: BettingMath }) {
  const counts = [...new Set(m.staking.map((s) => s.bets_per_week))].sort((a, b) => a - b)
  const [perWeek, setPerWeek] = useState<string>(String(counts.includes(6) ? 6 : (counts[0] ?? 6)))
  const rows = m.staking.filter((s) => String(s.bets_per_week) === perWeek)
  return (
    <Section title="How much to stake" help="Each rule is replayed over seasons drawn from history, starting from the same bankroll. The typical end is the middle outcome; the worst 5% is where the unluckiest one in twenty finished.">
      <Lede>18-week seasons replayed from history at each staking rule.</Lede>
      <div className="mb-3">
        <Segmented label="Bets a week" value={perWeek} onChange={setPerWeek} options={counts.map((c) => ({ value: String(c), label: `${c} bets a week` }))} />
      </div>
      <TableScroll>
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Rule</th>
              <th className={th}>Avg stake</th>
              <th className={th}>Lost half</th>
              <th className={th}>Ended down</th>
              <th className={th}>Typical end</th>
              <th className={th}>Worst 5%</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.strategy}>
                <td className={td}>{s.label}</td>
                <td className={`${td} tabular`}>{s.avg_stake_pct == null ? '–' : `${s.avg_stake_pct.toFixed(s.avg_stake_pct < 1 ? 2 : 1)}%`}</td>
                <td className={`${td} tabular`}>{chance(s.p_lose_half)}</td>
                <td className={`${td} tabular`}>{chance(s.p_down)}</td>
                <td className={`${td} tabular`}>{pct(s.median_end, 0)}</td>
                <td className={`${td} tabular`}>{pct(s.p5_end, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
      <p className="mt-2 text-[13px] text-ink-3">Typical end and worst 5% are shares of the starting bankroll: 100% is where you began.</p>
    </Section>
  )
}
