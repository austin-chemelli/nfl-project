import { DotWhisker } from '../../charts'
import { DataTable, ModelBadge, Section, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { llVsMarket } from '../../lib/format'
import { colorVar, LINES } from '../../lib/models'
import { label } from './names'

const signed = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)}`

export function Backtest({ t }: { t: Tracker; meta: Meta }) {
  const bt = t.backtest
  const market = bt.find((r) => r.model_id === 'market_baseline')
  const rows = bt.filter((r) => r.model_id !== 'market_baseline' && r.d_vs_market != null).sort((a, b) => a.d_vs_market! - b.d_vs_market!)
  if (!rows.length) return null
  const first = Math.min(...rows.map((r) => r.first_season))
  const last = Math.max(...rows.map((r) => r.last_season))
  const seasons = Math.max(...rows.map((r) => r.seasons))
  const games = Math.max(...rows.map((r) => r.n_games))
  return (
    <Section title="Backtest: how far each line sits from the market" help="Every game from 2005 on, scored by models that never trained on the season they predict.">
      <DotWhisker
        rows={rows.map((r) => ({
          key: r.model_id,
          label: <ModelBadge modelId={r.model_id} />,
          value: r.d_vs_market!,
          lo: r.d_lo ?? r.d_vs_market!,
          hi: r.d_hi ?? r.d_vs_market!,
          color: colorVar(r.model_id),
          title: `${label(r.model_id)}: ${signed(r.d_vs_market!)} vs the market (90% range ${signed(r.d_lo ?? 0)} to ${signed(r.d_hi ?? 0)}), ${r.n_games.toLocaleString('en-US')} games`,
        }))}
        format={signed}
        refLabel="The market"
        leftLabel="better than the market"
        rightLabel="worse than the market"
      />
      <p className="mt-2 text-[13px] text-ink-2">
        Log loss minus the market&apos;s, {first} to {last} ({seasons} seasons, up to {games.toLocaleString('en-US')} games per line). Whiskers are a 90% range from resampling whole seasons. The zero line is the market; an approach only beats it if its whole whisker sits left of the line.
      </p>
      <ul className="mt-2 list-disc pl-5 text-[14px]">
        {LINES.filter((m) => rows.some((r) => r.model_id === m)).map((m) => {
          const r = rows.find((x) => x.model_id === m)!
          return (
            <li key={m}>
              <strong>{label(m)}</strong>: {market ? llVsMarket(r.log_loss, market.log_loss) : r.log_loss.toFixed(3)} over {r.n_games.toLocaleString('en-US')} games and {r.seasons} seasons.
            </li>
          )
        })}
      </ul>
      <DataTable summary="Show the numbers: backtest">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Line</th>
              <th className={th}>Seasons</th>
              <th className={th}>Games</th>
              <th className={th}>Log loss</th>
              <th className={th}>vs market</th>
              <th className={th}>90% range</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.model_id}>
                <td className={td}><ModelBadge modelId={r.model_id} /></td>
                <td className={`${td} tabular`}>{r.seasons}</td>
                <td className={`${td} tabular`}>{r.n_games.toLocaleString('en-US')}</td>
                <td className={`${td} tabular`}>{r.log_loss.toFixed(4)}</td>
                <td className={`${td} tabular`}>{signed(r.d_vs_market!)}</td>
                <td className={`${td} tabular`}>{signed(r.d_lo ?? 0)} to {signed(r.d_hi ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
