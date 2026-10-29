import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { WeekEdge } from '../../diy'

const tick = { fill: 'var(--text-muted)', fontSize: 12 }

/** Edge over the market per game, by week: up = closer to what happened than the market. */
export function WeekChart({ rows }: { rows: WeekEdge[] }) {
  return (
    <div className="h-60 w-full" aria-hidden>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="week" tick={tick} axisLine={{ stroke: 'var(--border)' }} tickLine={false} interval="preserveStartEnd" />
          <YAxis tick={tick} axisLine={{ stroke: 'var(--border)' }} tickLine={false} width={48} tickFormatter={(v) => Number(v).toFixed(2)} />
          <ReferenceLine y={0} stroke="var(--text-muted)" />
          <Tooltip formatter={(v) => `${Number(v) >= 0 ? '+' : '−'}${Math.abs(Number(v)).toFixed(3)} per game`} labelFormatter={(l) => `Week ${l}`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }} />
          <Bar dataKey="edge" name="Edge vs market" isAnimationActive={false}>
            {rows.map((r) => <Cell key={r.week} fill={r.edge > 0 ? 'var(--div-pos)' : 'var(--div-neg)'} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
