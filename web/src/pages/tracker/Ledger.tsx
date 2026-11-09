import { DotWhisker } from '../../charts'
import { DataTable, ModelBadge, Section, td, th } from '../../components/ui'
import { Help } from '../../components/Help'
import type { Meta, Tracker } from '../../data/contract'
import { dash } from '../../lib/format'
import { colorVar, isReference } from '../../lib/models'
import { Bankroll } from './Bankroll'
import { betsVerdict, noEdgeReturn, returnRows, signedPct } from './bets'
import { KEY_LINES, label, REF_LINES, sentenceName } from './names'
import { SeasonGrid } from './SeasonGrid'

const signed = (v: number | null, d: number) => (v == null ? dash : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}`)
const pc = (v: number | null, d: number) => (v == null ? dash : `${v >= 0 ? '+' : '−'}${Math.abs(100 * v).toFixed(d)}%`)
const rate = (v: number | null | undefined) => (v == null ? dash : `${(100 * v).toFixed(1)}%`)

export function Ledger({ t, meta }: { t: Tracker; meta: Meta }) {
  const keep = new Set<string>([...KEY_LINES, ...REF_LINES])
  const order = [...KEY_LINES, ...REF_LINES] as string[]
  const rows = t.ledger
    .filter((r) => keep.has(r.model_id))
    .sort((a, b) => a.kind.localeCompare(b.kind) || (b.units ?? -1e9) - (a.units ?? -1e9) || order.indexOf(a.model_id) - order.indexOf(b.model_id))
  const seasons = (t.ledger_seasons ?? []).filter((r) => keep.has(r.model_id))
  const returns = returnRows(rows)
  const verdict = betsVerdict(rows, (id) => sentenceName(meta, id))
  const noEdge = noEdgeReturn(returns)
  const best = returns.map((r) => r.model_id)
  const ids = order.filter((m) => seasons.some((r) => r.model_id === m))
  const showClv = rows.some((r) => r.clv != null)
  return (
    <Section title="Paper bets" help="Pretend wagers: one unit when a line is over 5 points of win chance from the market (moneyline), else on the spread when it's 1.5+ spread points off. Starts 2006, the first priced season.">
      {verdict && <p className="text-lg font-medium">{verdict}</p>}
      {rows.length === 0 && <p className="mt-3 text-ink-2">No bets recorded yet.</p>}

      {seasons.length > 0 && (
        <>
          <h3 className="mt-6 font-medium"><Help text="Dotted: what the bookmaker's cut takes from similar bets. Above it beats blind betting, even at a loss. Steeper from 2023, when prices carry a bigger cut.">Bankroll over time</Help></h3>
          <p className="mt-1 text-[13px] text-ink-2">Running profit in units. Dotted: betting with no edge.</p>
          <Bankroll rows={seasons} ids={ids} />
        </>
      )}

      {returns.length > 0 && (
        <>
          <h3 className="mt-6 font-medium">Return per bet</h3>
          <p className="mt-1 mb-2 text-[13px] text-ink-2">
            Profit per unit, with a 90% range. An edge needs the whole range right of no edge.
          </p>
          <DotWhisker
            rows={returns.map((r) => ({
              key: r.model_id,
              label: <ModelBadge modelId={r.model_id} />,
              value: r.roi,
              lo: r.roi_lo,
              hi: r.roi_hi,
              color: colorVar(r.model_id),
              title: `${label(r.model_id)}: ${signedPct(r.roi)} a bet (90% range ${signedPct(r.roi_lo)} to ${signedPct(r.roi_hi)}), ${r.bets.toLocaleString('en-US')} bets`,
            }))}
            format={(v) => signedPct(v, 0)}
            refLabel="Break-even"
            leftLabel="losing"
            rightLabel="profit"
            marker={noEdge == null ? undefined : { value: noEdge, label: 'no edge' }}
          />
        </>
      )}

      {seasons.length > 0 && (
        <>
          <h3 className="mt-6 font-medium"><Help text="A season of bets is mostly luck. Bad years tend to hit every line at once, so one good year says little about a line.">Season by season</Help></h3>
          <p className="mt-1 text-[13px] text-ink-2">Units won or lost each season.</p>
          <SeasonGrid rows={seasons} ids={[...best, ...ids.filter((m) => !best.includes(m))]} current={t.season} />
        </>
      )}

      {rows.length > 0 && (
        <DataTable summary="Show the numbers: paper bets">
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Line</th>
                <th className={th}><Help text="Backfill = priced after the fact; live = placed at a real lock.">Kind</Help></th>
                <th className={th}><Help text="Games where the line differed enough from the market to bet.">Bets</Help></th>
                <th className={th}><Help text="Wins-losses-pushes.">Record</Help></th>
                <th className={th}><Help text="Share of decided bets won, and the share those prices needed to break even.">Won / needed</Help></th>
                <th className={th}><Help text="Profit in units; each bet risks 1 unit. Mostly noise.">Units</Help></th>
                <th className={th}><Help text="Profit divided by units staked (ROI).">Return</Help></th>
                {showClv && <th className={th}><Help text="Live moneyline bets: average move toward the bet between the lock and the closing price, in points of win probability. Positive means the approach beat the final market.">CLV</Help></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.model_id}-${r.kind}`}>
                  <td className={td}><ModelBadge modelId={r.model_id} reference={isReference(r.model_id)} /></td>
                  <td className={td}>{r.kind}</td>
                  <td className={`${td} tabular`}>{r.bets.toLocaleString('en-US')}</td>
                  <td className={`${td} tabular`}>{r.wins}-{r.losses}-{r.pushes}</td>
                  <td className={`${td} tabular whitespace-nowrap`}>{rate(r.win_rate)} / {rate(r.need_rate)}</td>
                  <td className={`${td} tabular`}>{signed(r.units, 1)}</td>
                  <td className={`${td} tabular`}>{pc(r.roi, 1)}</td>
                  {showClv && <td className={`${td} tabular`}>{pc(r.clv, 2)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      )}
    </Section>
  )
}
