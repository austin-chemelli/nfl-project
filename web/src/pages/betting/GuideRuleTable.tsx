import { TableScroll, td, th } from '../../components/ui'
import type { GuideRule } from '../../data/contract'
import { pct, signedPct } from '../../lib/format'

const GUIDE_ROWS = [
  ['worth_a_look', 'Worth a look'],
  ['coin_flip', 'Coin flip'],
  ['skip_mid_favorite', 'Skip: the middle favorite'],
] as const

/** What each group of the card's rule returned, by period. */
export function GuideRuleTable({ rows }: { rows: GuideRule }) {
  return (
    <TableScroll>
      <table className="w-full text-[13px]">
        <thead>
          <tr>
            <th className={th}>Group</th>
            <th className={th}>Period</th>
            <th className={th}>Bets</th>
            <th className={th}>Win rate</th>
            <th className={th}>Return</th>
            <th className={th}>90% range</th>
          </tr>
        </thead>
        <tbody>
          {GUIDE_ROWS.flatMap(([key, name]) =>
            rows[key].map((r) => (
              <tr key={`${key}-${r.period}`}>
                <td className={td}>{name}</td>
                <td className={`${td} tabular`}>{r.period.replace('-', '–')}</td>
                <td className={`${td} tabular`}>{r.n.toLocaleString('en-US')}</td>
                <td className={`${td} tabular`}>{pct(r.win_rate, 1)}</td>
                <td className={`${td} tabular`}>{signedPct(r.roi)}</td>
                <td className={`${td} tabular`}>{signedPct(r.roi_lo)} to {signedPct(r.roi_hi)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </TableScroll>
  )
}
