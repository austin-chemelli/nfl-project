import { ModelBadge, Section, TableScroll, td, th } from '../../components/ui'
import { Help } from '../../components/Help'
import type { Tracker } from '../../data/contract'
import { dash } from '../../lib/format'
import { KEY_LINES, REF_LINES } from './names'

const signed = (v: number | null, d: number) => (v == null ? dash : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}`)
const pc = (v: number | null, d: number) => (v == null ? dash : `${v >= 0 ? '+' : '−'}${Math.abs(100 * v).toFixed(d)}%`)

export function Ledger({ t }: { t: Tracker }) {
  const keep = new Set<string>([...KEY_LINES, ...REF_LINES])
  const order = [...KEY_LINES, ...REF_LINES] as string[]
  const rows = t.ledger
    .filter((r) => keep.has(r.model_id))
    .sort((a, b) => a.kind.localeCompare(b.kind) || (b.units ?? -1e9) - (a.units ?? -1e9) || order.indexOf(a.model_id) - order.indexOf(b.model_id))
  return (
    <Section title="Paper bets" help="Pretend wagers, no money involved. Profit and loss over a season is dominated by luck.">
      <p className="text-[14px] text-ink-2">
        <strong className="text-ink">Not betting advice; small samples.</strong> Each lock, every approach stakes a flat 1 unit on the moneyline wherever its win probability differs from the vig-free market by more than 5 points. Season profit and loss is mostly noise; closing-line value (CLV, whether the price you got beat the final price) is the better edge signal. Backfill bets are priced at nflverse&apos;s closing-ish line, so their ROI is a harsh lower bound and their CLV is undefined.
      </p>
      {rows.length === 0 ? (
        <p className="mt-3 text-ink-2">No bets recorded yet.</p>
      ) : (
        <TableScroll>
          <table className="mt-3 w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Line</th>
                <th className={th}><Help text="Backfill = priced after the fact; live = placed at a real lock.">Kind</Help></th>
                <th className={th}><Help text="Games where the approach differed from the market by 5+ points.">Bets</Help></th>
                <th className={th}><Help text="Wins-losses-pushes.">Record</Help></th>
                <th className={th}><Help text="Profit in units; each bet risks 1 unit. Mostly noise.">Units</Help></th>
                <th className={th}><Help text="Profit divided by units staked (ROI).">Return</Help></th>
                <th className={th}><Help text="Average edge versus the closing price; positive means the approach beat the final market.">CLV</Help></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.model_id}-${r.kind}`}>
                  <td className={td}><ModelBadge modelId={r.model_id} /></td>
                  <td className={td}>{r.kind}</td>
                  <td className={`${td} tabular`}>{r.bets.toLocaleString('en-US')}</td>
                  <td className={`${td} tabular`}>{r.wins}-{r.losses}-{r.pushes}</td>
                  <td className={`${td} tabular`}>{signed(r.units, 1)}</td>
                  <td className={`${td} tabular`}>{pc(r.roi, 1)}</td>
                  <td className={`${td} tabular`}>{pc(r.clv, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}
      <p className="mt-2 text-[13px] text-ink-2">
        Backfill rows cover every graded season in the backtest, not just this one. Live rows appear after the first graded locks. Losing a few percent into the market&apos;s price is what a model that trails the market looks like.
      </p>
    </Section>
  )
}
