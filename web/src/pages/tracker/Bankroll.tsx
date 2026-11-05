import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ModelBadge } from '../../components/ui'
import type { Tracker } from '../../data/contract'
import { APPROACHES, colorVar, dashArray } from '../../lib/models'
import { bankrollRows, liveNote } from './bets'
import { label } from './names'

type Row = NonNullable<Tracker['ledger_seasons']>[number]
const NO_EDGE = 'no_edge'
const units = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}`

/** Running paper profit by season, against what the bookmaker's cut alone would have taken. */
export function Bankroll({ rows, ids }: { rows: Row[]; ids: string[] }) {
  const chart = useMemo(() => bankrollRows(rows), [rows])
  const [shown, setShown] = useState<string[]>(() => ids.filter((m) => (APPROACHES as readonly string[]).includes(m)))
  const toggle = (m: string) => setShown((s) => (s.includes(m) ? s.filter((x) => x !== m) : [...s, m]))
  const seasons = chart.map((r) => r.season)
  const start = seasons[0]
  const live = new Map(chart.map((r) => [r.season, r.live]))
  return (
    <>
      <div className="mt-2 flex flex-wrap items-center gap-2" role="group" aria-label="Lines to show">
        {ids.map((m) => (
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
        <span className="flex items-center gap-1.5 px-1 text-[13px] text-ink-2">
          <svg width="22" height="6" aria-hidden="true"><line x1="0" x2="22" y1="3" y2="3" stroke="var(--text-muted)" strokeWidth="2" strokeDasharray="2 3" /></svg>
          No edge
        </span>
      </div>
      <div className="mt-2 h-80 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 320 }}>
          <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
            <ReferenceLine y={0} stroke="var(--text-muted)" strokeWidth={1.5} label={{ value: 'break-even', position: 'insideBottomRight', fill: 'var(--text-muted)', fontSize: 12 }} />
            <XAxis dataKey="season" type="number" domain={[Math.min(...seasons), Math.max(...seasons)]} allowDecimals={false} tickCount={8} tickFormatter={(s: number) => (s === start ? 'start' : String(s))} stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v: number) => (v === 0 ? '0' : units(v).replace('.0', ''))} stroke="var(--text-muted)" tick={{ fontSize: 12 }} width={48} label={{ value: 'Units', angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }} />
            <Tooltip
              formatter={(v, name) => [units(Number(v)), name === NO_EDGE ? 'No edge' : label(String(name))]}
              labelFormatter={(s) => (Number(s) === start ? 'Start' : `Through ${s}`) + liveNote(live.get(Number(s)) ?? 0)}
              itemSorter={(i) => -Number(i.value)}
              contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }}
            />
            <Line dataKey={NO_EDGE} name={NO_EDGE} type="linear" stroke="var(--text-muted)" strokeWidth={2} strokeDasharray="2 3" dot={false} isAnimationActive={false} />
            {shown.map((m) => (
              <Line key={m} dataKey={m} name={m} type="linear" stroke={colorVar(m)} strokeDasharray={dashArray(m)} strokeWidth={2} dot={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}
