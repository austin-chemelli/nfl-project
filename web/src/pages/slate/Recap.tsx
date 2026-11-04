/** Week recap above the slate grid (ADR 0016, 0017): a summary strip first, the full model table and lists behind a disclosure. */
import { Link } from 'react-router'
import { Help } from '../../components/Help'
import { SummaryStrip, Tile } from '../../components/SummaryStrip'
import { Card, ErrorBox, ModelBadge, TableScroll, td, th } from '../../components/ui'
import { isNotFound, useRecap } from '../../data/api'
import type { WeekRecap } from '../../data/contract'
import { dash } from '../../lib/format'
import { recapTiles } from './recapTiles'

export function Recap({ season, week }: { season: number; week: number }) {
  const q = useRecap(season, week)
  if (q.isPending) return null
  if (q.isError) return isNotFound(q.error) ? null : <ErrorBox error={q.error} />
  return <RecapBlock r={q.data} />
}

/** Log loss against the market: negative is better. */
function vsMarket(v: number | null | undefined): string {
  if (v == null) return dash
  if (Math.abs(v) < 0.0005) return 'same'
  return `${Math.abs(v).toFixed(3)} ${v < 0 ? 'better' : 'worse'}`
}

function RecapBlock({ r }: { r: WeekRecap }) {
  const models = [...r.models].sort((a, b) => (a.rank || 99) - (b.rank || 99))
  return (
    <div role="region" aria-label={`Week ${r.week} recap`} className="flex flex-col gap-3">
      <SummaryStrip label={`Week ${r.week} summary`}>
        {recapTiles(r).map((t) => <Tile key={t.id} label={t.label} value={t.value} sub={t.sub} modelId={t.modelId} />)}
      </SummaryStrip>
      <details className="text-[14px]">
        <summary className="cursor-pointer text-[13px] text-ink-3 hover:text-ink">Full recap</summary>
        <Card className="mt-2">
          <TableScroll>
            <table className="w-full border-collapse text-[14px]">
              <thead>
                <tr>
                  <th className={th}>Rank</th>
                  <th className={th}>Model</th>
                  <th className={th}>Picks right</th>
                  <th className={th}>
                    <Help text="How surprised the forecast was by the results, averaged: lower is better, 0.693 is a coin flip.">Log loss</Help>
                  </th>
                  <th className={th}>vs market</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => {
                  const ref = m.kind !== 'approach' && m.kind !== 'ensemble'
                  return (
                    <tr key={m.model_id} className={ref ? 'text-ink-3' : m.model_id === r.best_model ? 'bg-surface-2' : undefined}>
                      <td className={`${td} tabular`}>{m.rank || dash}</td>
                      <td className={td}>{ref ? m.label : <ModelBadge modelId={m.model_id} label={m.label} />}</td>
                      <td className={`${td} tabular whitespace-nowrap`}>{m.right} of {m.n}</td>
                      <td className={`${td} tabular`}>{m.log_loss.toFixed(3)}</td>
                      <td className={`${td} tabular whitespace-nowrap`}>{m.rank === 0 ? 'reference' : vsMarket(m.vs_market)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableScroll>
          <div className="mt-4 grid gap-4 border-t border-line pt-3 sm:grid-cols-2">
            <GameList title="Biggest upsets" rows={r.upsets.map((u) => ({ id: u.game_id, label: `${u.away} @ ${u.home}`, text: u.sentence }))} />
            <GameList title="Most misread" rows={r.misread.map((u) => ({ id: u.game_id, label: `${u.away} @ ${u.home}`, text: u.sentence }))} />
            <GameList title="Luckiest" rows={r.luckiest.map((t) => ({ id: t.game_id, label: t.team, text: t.sentence }))} />
            <GameList title="Unluckiest" rows={r.unluckiest.map((t) => ({ id: t.game_id, label: t.team, text: t.sentence }))} />
          </div>
          {r.note && <p className="mt-3 text-[13px] text-ink-3">{r.note}</p>}
        </Card>
      </details>
    </div>
  )
}

function GameList({ title, rows }: { title: string; rows: { id: string; label: string; text: string }[] }) {
  if (rows.length === 0) return null
  return (
    <div>
      <h3 className="text-[12px] font-medium uppercase tracking-wide text-ink-3">{title}</h3>
      <ul className="mt-1 flex flex-col gap-1.5 text-[14px]">
        {rows.map((x) => (
          <li key={`${x.id}-${x.label}`}>
            <Link to={`/game/${x.id}`} className="font-medium text-accent hover:underline">{x.label}</Link>{' '}
            <span className="text-ink-2">{x.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
