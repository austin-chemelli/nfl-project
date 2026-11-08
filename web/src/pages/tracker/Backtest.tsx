import { DotWhisker } from '../../charts'
import { DataTable, ModelBadge, Section, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { APPROACHES, colorVar, isPublicLine, isReference } from '../../lib/models'
import { label } from './names'

const signed = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)}`
// Data is log loss minus the market's (plus = worse); the chart and table flip it so plus = ahead, as on the season chart.
const ahead = (d: number) => -d

export function Backtest({ t }: { t: Tracker; meta: Meta }) {
  const bt = t.backtest
  const rows = bt.filter((r) => r.model_id !== 'market_baseline' && isPublicLine(r.model_id) && r.d_vs_market != null).sort((a, b) => a.d_vs_market! - b.d_vs_market!)
  if (!rows.length) return null
  const first = Math.min(...rows.map((r) => r.first_season))
  const last = Math.max(...rows.map((r) => r.last_season))
  const seasons = Math.max(...rows.map((r) => r.seasons))
  const games = Math.max(...rows.map((r) => r.n_games))
  return (
    <Section title="Backtest: how far each line sits from the market" help="Each line's log loss gap to the market over every decided game. Right of the line is ahead; a line beats the market only if its whole 90% range does.">
      <p className="mb-2 text-[14px] text-ink-2">Every decided game since 2005, each season scored with weights fitted on earlier ones.</p>
      <DotWhisker
        rows={rows.map((r) => ({
          key: r.model_id,
          label: <ModelBadge modelId={r.model_id} />,
          value: ahead(r.d_vs_market!),
          lo: ahead(r.d_hi ?? r.d_vs_market!),
          hi: ahead(r.d_lo ?? r.d_vs_market!),
          color: colorVar(r.model_id),
          title: `${label(r.model_id)}: gap ${signed(ahead(r.d_vs_market!))} (90% range ${r.d_hi == null || r.d_lo == null ? '–' : `${signed(ahead(r.d_hi))} to ${signed(ahead(r.d_lo))}`}), ${r.n_games.toLocaleString('en-US')} games`,
        }))}
        format={signed}
        refLabel="The market"
        leftLabel="behind the market"
        rightLabel="ahead of the market"
      />
      <p className="mt-2 text-[13px] text-ink-2">
        {first} to {last} · {seasons} seasons, up to {games.toLocaleString('en-US')} games a line
      </p>
      <ul className="mt-2 list-none p-0 text-[14px]">
        {APPROACHES.filter((m) => rows.some((r) => r.model_id === m)).map((m) => {
          const r = rows.find((x) => x.model_id === m)!
          const d = r.d_vs_market!
          return (
            <li key={m} className="tabular">
              <strong>{label(m)}</strong> {r.log_loss.toFixed(3)} · {Math.abs(d) < 0.0005 ? 'level' : `${Math.abs(d).toFixed(3)} ${d > 0 ? 'behind' : 'ahead'}`}
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
              <th className={th}>Gap to market</th>
              <th className={th}>90% range</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.model_id}>
                <td className={td}><ModelBadge modelId={r.model_id} reference={isReference(r.model_id)} /></td>
                <td className={`${td} tabular`}>{r.seasons}</td>
                <td className={`${td} tabular`}>{r.n_games.toLocaleString('en-US')}</td>
                <td className={`${td} tabular`}>{r.log_loss.toFixed(4)}</td>
                <td className={`${td} tabular`}>{signed(ahead(r.d_vs_market!))}</td>
                <td className={`${td} tabular`}>{r.d_hi == null || r.d_lo == null ? '–' : `${signed(ahead(r.d_hi))} to ${signed(ahead(r.d_lo))}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
