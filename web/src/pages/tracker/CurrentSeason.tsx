import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DataTable, ModelBadge, Section, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { colorVar, dashArray, isPublicLine, isReference } from '../../lib/models'
import { currentSummary, gapLimit, gapRows, GAP_BAND, signedGap } from './helpers'
import { KEY_LINES, label } from './names'

// A hover on the table header: the lede's help has the same facts, this is the column's own definition.
const HELP_LL = 'Log loss punishes confident wrong calls hardest. Lower is better; 0.693 is a coin flip, and the market scores about 0.61. Gaps under 0.025 are too close to call.'

export function CurrentSeason({ t }: { t: Tracker; meta: Meta }) {
  const cur = t.current_season
  const chart = useMemo(() => gapRows(cur), [cur])
  const summary = useMemo(() => currentSummary(cur), [cur])
  const ids = useMemo(() => new Set(cur.map((r) => r.model_id)), [cur])
  const [shown, setShown] = useState<string[]>(() => [...KEY_LINES, 'elo_v0'].filter((m) => m !== 'market_baseline' && ids.has(m)))
  const title = `${t.season} so far`

  if (!cur.length) {
    return (
      <Section title={title} help="Games already played this season, each scored against the market.">
        <p className="text-ink-2">No graded games this season yet.</p>
      </Section>
    )
  }

  const weeks = chart.map((r) => r.week)
  const firstLive = cur.filter((r) => r.live).map((r) => r.week).sort((a, b) => a - b)[0]
  const liveWeeks = new Set(cur.filter((r) => r.live).map((r) => r.week))
  const lim = gapLimit(chart, shown)
  const order = (m: string) => {
    const i = [...KEY_LINES, 'elo_v0', 'home_naive'].indexOf(m)
    return i < 0 ? 99 : i // unlisted lines (the diagnostic global fit) go last
  }
  const rows = summary.rows.filter((r) => isPublicLine(r.model_id)).sort((a, b) => order(a.model_id) - order(b.model_id))
  const toggle = (m: string) => setShown((s) => (s.includes(m) ? s.filter((x) => x !== m) : [...s, m]))

  return (
    <Section title={title} help="Games already played this season, each scored against the market.">
      {/* With live games, the Live tile above already says the split. */}

      <h3 className="mt-6 font-medium">Gap to the market, by week</h3>
      <p className="mt-1 text-[13px] text-ink-2">
        Each line&apos;s running gap to the market; above zero is ahead.
      </p>
      <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Lines to show">
        {[...ids].sort((a, b) => order(a) - order(b)).filter((m) => m !== 'market_baseline' && isPublicLine(m)).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={shown.includes(m)}
            onClick={() => toggle(m)}
            className={`rounded-md border px-2 py-0.5 text-[13px] ${shown.includes(m) ? 'border-ink-3 bg-surface-2 text-ink' : 'border-line text-ink-3'}`}
          >
            <ModelBadge modelId={m} />
          </button>
        ))}
      </div>
      {chart.length === 0 ? (
        <p className="mt-2 text-ink-2">No week has a market line to compare against yet.</p>
      ) : (
      <div className="mt-2 h-80 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 320 }}>
          <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
            <ReferenceArea y1={GAP_BAND} y2={lim} fill="var(--good)" fillOpacity={0.07} stroke="none" label={{ value: 'ahead of the market ↑', position: 'insideTopLeft', fill: 'var(--text-muted)', fontSize: 12 }} />
            <ReferenceArea y1={-GAP_BAND} y2={GAP_BAND} fill="var(--border)" fillOpacity={0.6} stroke="none" label={{ value: 'too close to call', position: 'insideTopRight', fill: 'var(--text-muted)', fontSize: 12 }} />
            <ReferenceArea y1={-lim} y2={-GAP_BAND} fillOpacity={0} stroke="none" label={{ value: 'behind ↓', position: 'insideBottomLeft', fill: 'var(--text-muted)', fontSize: 12 }} />
            <ReferenceLine y={0} stroke="var(--text-muted)" strokeWidth={1.5} />
            {firstLive != null && (
              <ReferenceLine x={firstLive} stroke="var(--text-muted)" strokeDasharray="5 4" label={{ value: `live from week ${firstLive}`, position: 'insideTopRight', fill: 'var(--text-muted)', fontSize: 12 }} />
            )}
            <XAxis dataKey="week" type="number" domain={[Math.min(...weeks) - 0.5, Math.max(...weeks) + 0.5]} allowDecimals={false} stroke="var(--text-muted)" tick={{ fontSize: 12 }} label={{ value: 'Week', position: 'insideBottom', offset: -2, fill: 'var(--text-muted)', fontSize: 12 }} />
            <YAxis domain={[-lim, lim]} ticks={[-lim, -lim / 2, 0, lim / 2, lim]} allowDataOverflow tickFormatter={(v: number) => (v === 0 ? '0' : signedGap(v).replace(/0+$/, ''))} stroke="var(--text-muted)" tick={{ fontSize: 12 }} width={58} />
            <Tooltip formatter={(v, name) => [signedGap(Number(v)), label(String(name))]} labelFormatter={(w) => `Week ${w}${liveWeeks.has(Number(w)) ? ' (live)' : ''}`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }} />
            {shown.map((m) => (
              <Line
                key={m}
                dataKey={m}
                name={m}
                type="monotone"
                stroke={colorVar(m)}
                strokeDasharray={dashArray(m)}
                strokeWidth={2}
                dot={(p: { cx?: number; cy?: number; payload?: { week: number }; index?: number }) =>
                  p.payload && liveWeeks.has(p.payload.week) && p.cx != null && p.cy != null ? (
                    <path key={`${m}-${p.index}`} d={`M${p.cx} ${p.cy - 5}L${p.cx + 5} ${p.cy}L${p.cx} ${p.cy + 5}L${p.cx - 5} ${p.cy}Z`} fill={colorVar(m)} />
                  ) : (
                    <g key={`${m}-${p.index}`} />
                  )
                }
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      )}
      <DataTable summary="Show the numbers: this season so far">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Line</th>
              <th className={th}>Games</th>
              <th className={th} title={HELP_LL}>Log loss</th>
              <th className={th}>vs the market</th>
              <th className={th}>Live weeks</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.model_id}>
                <td className={td}><ModelBadge modelId={r.model_id} reference={isReference(r.model_id)} /></td>
                <td className={`${td} tabular`}>{r.games}</td>
                <td className={`${td} tabular`}>{r.logLoss.toFixed(3)}</td>
                <td className={td}>{r.model_id === 'market_baseline' ? 'reference' : (r.vsMarket ?? '–').replace(/^[\d.]+ /, '')}</td>
                <td className={`${td} tabular`}>{r.liveWeeks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
