import { TableScroll, td, th } from '../../components/ui'
import type { BettingWeek } from '../../data/contract'
import { signedPct, signedUnits } from '../../lib/format'
import { VERDICT_NAMES } from './weekFacts'

/** The card's own paper record at the locks, by verdict: one unit a bet at the consensus price. */
export function PaperRecord({ w }: { w: BettingWeek }) {
  const rows = w.record.summary
  if (rows.length === 0) return <p className="text-[14px] text-ink-2">No graded card bets yet this season.</p>
  return (
    <TableScroll>
      <table className="w-full text-[13px]">
        <thead>
          <tr>
            <th className={th}>Card</th>
            <th className={th}>Bets</th>
            <th className={th}>Won–lost</th>
            <th className={th}>Units</th>
            <th className={th}>Return</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.verdict}>
              <td className={td}>{VERDICT_NAMES[r.verdict] ?? r.verdict}</td>
              <td className={`${td} tabular`}>{r.bets}</td>
              <td className={`${td} tabular`}>{r.wins}–{r.losses}</td>
              <td className={`${td} tabular`}>{signedUnits(r.units)}</td>
              <td className={`${td} tabular`}>{signedPct(r.roi)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  )
}
