import { useId, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, DataTable, Section, StatTile, td, th } from '../../components/ui'
import { Help } from '../../components/Help'
import type { Hypotheses } from '../../data/contract'
import { bestWorst, chartRows, itemName, itemOptions, searchOptions, skillText, type ChartRow } from './helpers'

const INPUT = 'rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink'

function SeasonChart({ rows, field, title, refValue, avg, label }: {
  rows: ChartRow[]; field: 'edge' | 'skill'; title: string; refValue: number; avg: number | null; label: string
}) {
  const fmt = (v: number) => (field === 'edge' ? `${v.toFixed(0)}%` : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(0)}%`)
  return (
    <div>
      <h3 className="mb-1 text-[14px] font-medium">{title}</h3>
      <div className="h-56 w-full" role="img" aria-label={`${label}: ${title} by season. The numbers are in the table below the charts.`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" vertical={false} />
            <XAxis dataKey="season" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} interval="preserveStartEnd" minTickGap={16} stroke="var(--border)" />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} tickFormatter={fmt} width={48} stroke="var(--border)" domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }}
              formatter={(v) => [typeof v === 'number' ? (field === 'edge' ? `${v.toFixed(1)}%` : skillText(v)) : '–', title]}
              labelFormatter={(s) => {
                const r = rows.find((x) => x.season === s)
                return `${s}${r ? `: ${r.nEdge} games with an edge, ${r.nGames} games` : ''}`
              }}
            />
            <ReferenceLine y={refValue} stroke="var(--text-muted)" label={{ value: field === 'edge' ? '50% = coin flip' : '0 = no better than baseline', position: 'insideTopLeft', fill: 'var(--text-muted)', fontSize: 11 }} />
            {avg != null && <ReferenceLine y={avg} stroke="var(--accent)" strokeDasharray="3 3" label={{ value: `average ${fmt(avg)}`, position: 'insideBottomRight', fill: 'var(--accent)', fontSize: 11 }} />}
            <Line type="monotone" dataKey={field} stroke="var(--accent)" strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export function OverTime({ h, itemKey, onPick }: { h: Hypotheses; itemKey: string | null; onPick: (key: string) => void }) {
  const [q, setQ] = useState('')
  const searchId = useId()
  const selectId = useId()
  const items = h.by_season.items
  const options = itemOptions(items)
  const it = itemKey ? items[itemKey] : undefined
  // Keep the chosen item selectable even when the search text would hide it.
  const visible = searchOptions(options, q)
  const shown = itemKey && !visible.some((o) => o.key === itemKey) ? [...visible, ...options.filter((o) => o.key === itemKey)] : visible
  const groups = shown.filter((o) => o.kind === 'group')
  const feats = shown.filter((o) => o.kind !== 'group')

  return (
    <Section
      title="Look at one thing over time"
      help="Pick a single feature or a whole group and see how well it predicts on its own, season by season. Each season is scored by a model trained only on the seasons before it, so nothing peeks ahead."
    >
      <p className="mb-3 max-w-3xl text-ink-2">
        Some years a signal does more than others. Groups are the high-level beliefs the personas weight; features are the single measurements inside them.
      </p>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label htmlFor={searchId} className="flex flex-col gap-1 text-[13px] text-ink-3">
          Search
          <input id={searchId} type="search" className={INPUT} placeholder="e.g. rest, EPA, quarterback" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label htmlFor={selectId} className="flex min-w-0 flex-col gap-1 text-[13px] text-ink-3">
          Feature or group
          <select id={selectId} className={`${INPUT} max-w-full`} value={itemKey ?? ''} onChange={(e) => onPick(e.target.value)}>
            {groups.length > 0 && <optgroup label="Groups">{groups.map((o) => <option key={o.key} value={o.key}>{o.name}</option>)}</optgroup>}
            {feats.length > 0 && <optgroup label="Features">{feats.map((o) => <option key={o.key} value={o.key}>{o.name}</option>)}</optgroup>}
          </select>
        </label>
      </div>
      {!it ? (
        <p className="text-ink-2">No season-by-season series yet.</p>
      ) : (
        <OverTimeBody h={h} it={it} />
      )}
    </Section>
  )
}

function OverTimeBody({ h, it }: { h: Hypotheses; it: Hypotheses['by_season']['items'][string] }) {
  const rows = chartRows(it, h.by_season.first_scored)
  const { best, worst } = bestWorst(it)
  const p = it.pooled
  const pooledEdge = p.edge_win_rate == null ? null : 100 * p.edge_win_rate
  const pooledSkill = p.skill_pct ?? null
  const bySeason = new Map(it.series.map((s) => [s.season, s]))
  const name = itemName(it)
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-3xl">
        <span className="font-medium"><Help text={it.description}>{name}</Help>:</span> <span className="text-ink-2">{it.sentence}</span>
      </p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Edge team won" value={pooledEdge == null ? '–' : `${pooledEdge.toFixed(1)}%`} sub={`across all seasons; 50% is a coin flip`} help="Of the games where this favored one side, how often that side won." />
        <StatTile label="Better than baseline" value={skillText(pooledSkill)} sub="vs always giving the home team its usual rate" help="How much better the one-feature model's probabilities are than the home-rate baseline. Above 0 is better." />
        <StatTile label="Best season" value={best ?? '–'} sub={best != null ? skillText(bySeason.get(best)?.skill_pct) : undefined} />
        <StatTile label="Worst season" value={worst ?? '–'} sub={worst != null ? skillText(bySeason.get(worst)?.skill_pct) : undefined} />
      </div>
      <Card className="flex flex-col gap-5">
        <SeasonChart rows={rows} field="edge" title="How often the team with the edge won" refValue={50} avg={pooledEdge} label={name} />
        <SeasonChart rows={rows} field="skill" title="Better than picking the home team at its usual rate" refValue={0} avg={pooledSkill} label={name} />
        <p className="text-[13px] text-ink-3">
          Top: of the games where the feature favored one side, how often that side won (50% = no better than a coin flip). Bottom: how much better the one-feature model's probabilities are than always giving the home team its historical win rate; above zero is better. Dotted line is the all-season average. Gaps are seasons without enough data (for example, charting data that starts in 2022).
        </p>
        <DataTable>
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Season</th>
                <th className={th}>Games</th>
                <th className={th}>With an edge</th>
                <th className={th}>Edge team won</th>
                <th className={th}>vs baseline</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.season}>
                  <td className={td}>{r.season}</td>
                  <td className={`${td} tabular`}>{r.nGames || '–'}</td>
                  <td className={`${td} tabular`}>{r.nGames ? r.nEdge : '–'}</td>
                  <td className={`${td} tabular`}>{r.edge == null ? '–' : `${r.edge.toFixed(1)}%`}</td>
                  <td className={`${td} tabular`}>{skillText(r.skill)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </Card>
    </div>
  )
}
