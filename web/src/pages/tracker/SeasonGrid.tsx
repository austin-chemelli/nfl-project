import { ModelBadge, TableScroll } from '../../components/ui'
import type { Tracker } from '../../data/contract'
import { cellFill, signedUnits } from './bets'
import { label } from './names'

type Row = NonNullable<Tracker['ledger_seasons']>[number]

/** Units per line per season: one row a line, so a shared bad year reads as a stripe down the grid. */
export function SeasonGrid({ rows, ids, current }: { rows: Row[]; ids: string[]; current: number }) {
  const seasons = [...new Set(rows.map((r) => r.season))].sort((a, b) => a - b)
  const at = new Map(rows.map((r) => [`${r.model_id}|${r.season}`, r]))
  return (
    <TableScroll>
      <table className="mt-2 w-full border-separate border-spacing-[2px] text-[12px]">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-surface-0 pr-2 text-left font-normal text-ink-3">Line</th>
            {seasons.map((s) => (
              <th key={s} scope="col" title={s === current ? `${s} so far` : String(s)} className="tabular min-w-[30px] font-normal text-ink-3">
                {`'${String(s).slice(2)}`}
              </th>
            ))}
            <th className="whitespace-nowrap pl-2 text-right font-normal text-ink-3">Up seasons</th>
          </tr>
        </thead>
        <tbody>
          {ids.map((m) => {
            const mine = seasons.map((s) => at.get(`${m}|${s}`))
            const up = mine.filter((r) => r && r.units > 0).length
            const played = mine.filter(Boolean).length
            return (
              <tr key={m}>
                <th scope="row" className="sticky left-0 z-10 whitespace-nowrap bg-surface-0 pr-2 text-left font-normal">
                  <ModelBadge modelId={m} />
                </th>
                {seasons.map((s, i) => {
                  const r = mine[i]
                  if (!r) return <td key={s} className="text-center text-ink-3">·</td>
                  return (
                    <td
                      key={s}
                      title={`${label(m)}, ${s}${s === current ? ' so far' : ''}: ${r.units >= 0 ? '+' : '−'}${Math.abs(r.units).toFixed(1)} units on ${r.bets} bets`}
                      style={{ background: cellFill(r.units) }}
                      className="tabular rounded-[3px] py-1 text-center text-ink"
                    >
                      {signedUnits(r.units)}
                    </td>
                  )
                })}
                <td className="tabular whitespace-nowrap pl-2 text-right text-ink-2">{up} of {played}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </TableScroll>
  )
}
