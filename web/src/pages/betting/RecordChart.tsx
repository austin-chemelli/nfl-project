import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BettingWeek } from '../../data/contract'
import { signedPct } from '../../lib/format'
import { axis, tip } from './facts'
import { recordRows } from './weekFacts'

const SERIES = [
  { key: 'history', label: 'History (re-ranked each season)', color: 'var(--accent)' },
  { key: 'live', label: '2026 at our locks', color: 'var(--series-student)' },
] as const

export function RecordChart({ w }: { w: BettingWeek }) {
  const rows = recordRows(w)
  const summary = rows.map((r) => `${r.name}: ${signedPct(r.history)} in history${r.live != null ? `, ${signedPct(r.live)} this season` : ''}`).join('; ')
  const live = rows.some((r) => r.live != null)
  return (
    <div>
      <div role="img" aria-label={`Return per bet. ${summary}`} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 256 }}>
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" horizontal={false} />
            <ReferenceLine x={0} stroke="var(--text-muted)" strokeWidth={1.5} />
            <XAxis type="number" tickFormatter={(v: number) => signedPct(v, 0)} {...axis} />
            <YAxis type="category" dataKey="name" width={104} {...axis} />
            <Tooltip formatter={(v, name) => [signedPct(Number(v)), String(name)]} contentStyle={tip} cursor={{ fill: 'var(--surface-2)' }} />
            {SERIES.filter((s) => s.key === 'history' || live).map((s) => (
              <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-ink-2">
        {SERIES.filter((s) => s.key === 'history' || live).map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
