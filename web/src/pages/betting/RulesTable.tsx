import { TableScroll, td, th } from '../../components/ui'
import type { GuideRules, RuleStat } from '../../data/contract'
import { signedPct } from '../../lib/format'

const ROWS: [keyof GuideRules & string, string][] = [
  ['target', 'Target (all)'],
  ['lean_dog', 'Underdog lean'],
  ['lean', 'Other small lean'],
  ['no_view', 'No view'],
  ['mid_fav', '−120 to −185'],
  ['long', '+185 or longer'],
  ['big_gap', 'Big disagreement'],
  ['model_pick', "The Student's pick everywhere"],
]

/** What each group of the card's rules returned in history, by period. */
export function RulesTable({ rules }: { rules: GuideRules }) {
  return (
    <TableScroll>
      <table className="w-full text-[13px]">
        <thead>
          <tr>
            <th className={th}>Group</th>
            <th className={th}>Bets</th>
            <th className={th}>Return</th>
            <th className={th}>2006–2015</th>
            <th className={th}>2016–2025</th>
            <th className={th}>2021–2025</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([key, name]) => {
            const r = rules[key] as RuleStat
            return (
              <tr key={key}>
                <td className={td}>{name}</td>
                <td className={`${td} tabular`}>{r.n.toLocaleString('en-US')}</td>
                <td className={`${td} tabular`}>{signedPct(r.roi)}</td>
                <td className={`${td} tabular`}>{signedPct(r.roi_first)}</td>
                <td className={`${td} tabular`}>{signedPct(r.roi_second)}</td>
                <td className={`${td} tabular`}>{signedPct(r.roi_2021_2025)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </TableScroll>
  )
}
