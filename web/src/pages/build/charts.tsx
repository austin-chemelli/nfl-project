/** Recharts wrappers for the Build page. Colors come from CSS variables, never hex. */
import { Bar, BarChart, Cell, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'
import { rampColor } from './points'

const tick = { fill: 'var(--text-muted)', fontSize: 12 }
const axisLine = { stroke: 'var(--border)' }

export function BudgetDonut({ rows }: { rows: { heading: string; share: number }[] }) {
  const data = rows.filter((r) => r.share > 0)
  return (
    <div className="h-56 w-full" aria-hidden>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <PieChart>
          <Pie data={data} dataKey="share" nameKey="heading" innerRadius="55%" outerRadius="90%" startAngle={90} endAngle={-270} stroke="var(--surface-1)" strokeWidth={2} isAnimationActive={false}>
            {data.map((r) => (
              <Cell key={r.heading} fill={rampColor(rows.findIndex((x) => x.heading === r.heading), rows.length)} />
            ))}
          </Pie>
          <Tooltip formatter={(v) => `${Number(v).toFixed(0)}%`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Edge over the market per season (market log loss minus yours): up = better. */
export function SeasonEdgeBars({ rows }: { rows: { season: number; edge: number }[] }) {
  return (
    <div className="h-64 w-full" aria-hidden>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="season" tick={tick} axisLine={axisLine} tickLine={false} interval="preserveStartEnd" minTickGap={12} />
          <YAxis tick={tick} axisLine={axisLine} tickLine={false} width={48} tickFormatter={(v) => Number(v).toFixed(2)} />
          <ReferenceLine y={0} stroke="var(--text-muted)" />
          <Tooltip formatter={(v) => `${Number(v) >= 0 ? '+' : '−'}${Math.abs(Number(v)).toFixed(4)}`} labelFormatter={(l) => `${l} season`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }} />
          <Bar dataKey="edge" name="Edge vs market" isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.season} fill={r.edge > 0 ? 'var(--div-pos)' : 'var(--div-neg)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Reliability: when you said X%, how often the home team won. The diagonal is perfect calibration. */
export function ReliabilityChart({ rows }: { rows: { mean: number; hit: number; ideal: number }[] }) {
  return (
    <div className="h-64 w-full" aria-hidden>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" />
          <XAxis dataKey="mean" type="number" domain={[0, 100]} tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={(v) => `${v}%`} />
          <YAxis type="number" domain={[0, 100]} tick={tick} axisLine={axisLine} tickLine={false} width={44} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v) => `${Number(v).toFixed(0)}%`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }} />
          <Line dataKey="ideal" name="Perfectly calibrated" stroke="var(--series-ref)" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          <Line dataKey="hit" name="Home team won" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
