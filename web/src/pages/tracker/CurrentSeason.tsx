import { useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DataTable, ModelBadge, Section, StatTile, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { colorVar, dashArray } from '../../lib/models'
import { currentSummary, headlineSentence } from './helpers'
import { KEY_LINES, label, sentenceName } from './names'

const HELP_LL =
  'Log loss is the scoring rule: it punishes confident wrong calls hard. Lower is better; 0.693 is a coin flip. The market scores about 0.61, so read every number as a distance from the market. Differences under 0.005 are noise at this sample size.'

export function CurrentSeason({ t, meta }: { t: Tracker; meta: Meta }) {
  const cur = t.current_season
  const summary = useMemo(() => currentSummary(cur), [cur])
  const ids = useMemo(() => new Set(cur.map((r) => r.model_id)), [cur])
  const [shown, setShown] = useState<string[]>(() => [...KEY_LINES, 'elo_v0'].filter((m) => ids.has(m)))
  const title = `${t.season} so far`

  if (!cur.length) {
    return (
      <Section title={title} help="Games already played this season, each scored against the market.">
        <p className="text-ink-2">No graded games this season yet.</p>
      </Section>
    )
  }

  const focus = summary.rows.find((r) => r.model_id === 'analyst') ?? summary.rows.find((r) => r.model_id !== 'market_baseline')
  const weeks = [...new Set(cur.map((r) => r.week))].sort((a, b) => a - b)
  const firstLive = cur.filter((r) => r.live).map((r) => r.week).sort((a, b) => a - b)[0]
  const backEnd = (firstLive ?? Math.max(...weeks) + 1) - 0.5
  const chart = weeks.map((w) => {
    const row: Record<string, number> = { week: w }
    for (const r of cur) if (r.week === w) row[r.model_id] = r.cum_log_loss
    return row
  })
  const liveWeeks = new Set(cur.filter((r) => r.live).map((r) => r.week))
  const order = (m: string) => {
    const i = [...KEY_LINES, 'elo_v0', 'home_naive'].indexOf(m)
    return i < 0 ? 99 : i // unlisted lines (the diagnostic global fit) go last
  }
  const rows = [...summary.rows].sort((a, b) => order(a.model_id) - order(b.model_id))
  const toggle = (m: string) => setShown((s) => (s.includes(m) ? s.filter((x) => x !== m) : [...s, m]))

  return (
    <Section title={title} help="Games already played this season, each scored against the market.">
      {focus && <p className="text-lg font-medium">{headlineSentence(focus, sentenceName(meta, focus.model_id))}</p>}
      <p className="mt-1 text-[13px] text-ink-2">
        {summary.liveGames === 0
          ? 'No live locks have been graded yet, so every number here is backfill: frozen models scored after the fact on this season\'s games. Differences under 0.005 are noise.'
          : `${summary.liveGames} live ${summary.liveGames === 1 ? 'game has' : 'games have'} been graded from locks made before kickoff (${summary.liveWeeks} ${summary.liveWeeks === 1 ? 'week' : 'weeks'}); the rest are backfill. That is far too few to rank anyone.`}
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {rows.filter((r) => (KEY_LINES as readonly string[]).includes(r.model_id)).map((r) => (
          <StatTile
            key={r.model_id}
            label={label(r.model_id)}
            help={r.model_id === 'market_baseline' ? 'The betting market with the bookmaker\'s cut removed. The reference line, never an input to any approach.' : meta.approaches.find((a) => a.id === r.model_id)?.blurb}
            value={r.logLoss.toFixed(3)}
            sub={r.delta == null ? 'reference' : Math.abs(r.delta) < 0.005 ? 'about the same as the market' : `${Math.abs(r.delta).toFixed(3)} ${r.delta > 0 ? 'worse' : 'better'}`}
          />
        ))}
      </div>

      <h3 className="mt-6 font-medium">Cumulative log loss by week</h3>
      <p className="text-[13px] text-ink-2">Running average since week 1; lower is better. Compare every line with the gray Market line.</p>
      <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Lines to show">
        {[...ids].sort((a, b) => order(a) - order(b)).filter((m) => m !== 'global').map((m) => (
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
      <div className="mt-2 h-80 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 320 }}>
          <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
            <ReferenceArea x1={Math.min(...weeks) - 0.5} x2={backEnd} fill="var(--border)" fillOpacity={0.35} label={{ value: 'backfill', position: 'insideTopLeft', fill: 'var(--text-muted)', fontSize: 12 }} />
            <XAxis dataKey="week" type="number" domain={[Math.min(...weeks) - 0.5, Math.max(...weeks) + 0.5]} allowDecimals={false} stroke="var(--text-muted)" tick={{ fontSize: 12 }} label={{ value: 'Week', position: 'insideBottom', offset: -2, fill: 'var(--text-muted)', fontSize: 12 }} />
            <YAxis domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(2)} stroke="var(--text-muted)" tick={{ fontSize: 12 }} width={44} />
            <Tooltip formatter={(v, name) => [Number(v).toFixed(3), label(String(name))]} labelFormatter={(w) => `Week ${w}${liveWeeks.has(Number(w)) ? ' (live)' : ''}`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }} />
            <Legend formatter={(v) => label(String(v))} wrapperStyle={{ fontSize: 12 }} />
            {shown.map((m) => (
              <Line
                key={m}
                dataKey={m}
                name={m}
                type="monotone"
                stroke={colorVar(m)}
                strokeDasharray={dashArray(m)}
                strokeWidth={m === 'market_baseline' ? 2.5 : 2}
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
      <p className="text-[13px] text-ink-2">
        Shaded weeks are backfill: models frozen before the season, scored after the fact. Diamonds mark live weeks, graded from locks made before kickoff. A handful of 16-game weeks is very noisy; lines crossing early means little.
      </p>
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
                <td className={td}><ModelBadge modelId={r.model_id} /></td>
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
