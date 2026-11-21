import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DataTable, Section, td, th } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct, signedPct, signedUnits } from '../../lib/format'
import { Key, Lede } from './common'
import { axis, chance, tip } from './facts'

const NAMES: Record<string, string> = { actual: 'What parlays returned', compounded: 'If the cut simply compounded', fair: 'A fair coin at −110' }

/** The same picks, combined: the cut compounds with every leg. */
export function Parlays({ m }: { m: BettingMath }) {
  const rows = useMemo(() => {
    const legs = [...new Set([...m.parlays.map((p) => p.legs), ...m.vig_compounding.map((v) => v.legs)])].sort((a, b) => a - b)
    return legs.map((n) => {
      const p = m.parlays.find((x) => x.legs === n)
      return { legs: n, actual: p?.roi ?? null, compounded: p?.compounded_single_roi ?? null, fair: m.vig_compounding.find((v) => v.legs === n)?.roi ?? null }
    })
  }, [m])
  return (
    <Section title="Parlays" help="A parlay pays only if every leg wins. Return is profit per dollar staked, over every parlay of the model's picks that history allows.">
      <Lede>The same picks, combined: the cut compounds with every leg.</Lede>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 288 }}>
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
            <ReferenceLine y={0} stroke="var(--text-muted)" strokeWidth={1.5} />
            <XAxis dataKey="legs" type="number" domain={[1, 'dataMax']} allowDecimals={false} tickFormatter={(n: number) => `${n} ${n === 1 ? 'leg' : 'legs'}`} {...axis} />
            <YAxis tickFormatter={(v: number) => signedPct(v, 0)} width={52} {...axis} />
            <Tooltip formatter={(v, name) => [signedPct(Number(v)), NAMES[String(name)] ?? String(name)]} labelFormatter={(n) => `${n} ${Number(n) === 1 ? 'leg' : 'legs'}`} contentStyle={tip} />
            <Line dataKey="compounded" name="compounded" type="linear" stroke="var(--accent-2)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="fair" name="fair" type="linear" stroke="var(--text-muted)" strokeWidth={2} strokeDasharray="2 3" dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="actual" name="actual" type="linear" stroke="var(--accent)" strokeWidth={2.5} dot={{ r: 3.5 }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Key
        items={[
          { label: NAMES.actual, color: 'var(--accent)' },
          { label: NAMES.compounded, color: 'var(--accent-2)' },
          { label: NAMES.fair, color: 'var(--text-muted)', dashed: true },
        ]}
      />
      <DataTable summary="Show the numbers: parlays">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Legs</th>
              <th className={th}>Return</th>
              <th className={th}>Hit rate</th>
              <th className={th}>Market&apos;s hit rate</th>
              <th className={th}>Losing season</th>
              <th className={th}>Down 10+ units</th>
              <th className={th}>Typical season</th>
            </tr>
          </thead>
          <tbody>
            {m.parlays.map((p) => (
              <tr key={p.legs}>
                <td className={`${td} tabular`}>{p.legs}</td>
                <td className={`${td} tabular`}>{signedPct(p.roi)}</td>
                <td className={`${td} tabular`}>{pct(p.hit_rate, 1)}</td>
                <td className={`${td} tabular`}>{pct(p.market_hit_rate, 1)}</td>
                <td className={`${td} tabular`}>{chance(p.p_losing_season)}</td>
                <td className={`${td} tabular`}>{chance(p.p_season_down_10u)}</td>
                <td className={`${td} tabular`}>{signedUnits(p.median_season_units, 1)} units</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
