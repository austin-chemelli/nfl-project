import { useMemo, useState } from 'react'
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { DataTable, ModelBadge, Section, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { colorVar } from '../../lib/models'
import { calibrationVerdict, foldReliability } from './helpers'
import { KEY_LINES, label, sentenceName } from './names'

const PC = (v: number) => `${Math.round(100 * v)}%`

export function Calibration({ t, meta }: { t: Tracker; meta: Meta }) {
  const avail = useMemo(() => KEY_LINES.filter((m) => t.reliability.some((r) => r.model_id === m)), [t.reliability])
  const [sel, setSel] = useState<string[]>(() => ['market_baseline', 'traditionalist', 'sharp'].filter((m) => avail.includes(m as never)))
  if (!avail.length) return null
  const folded = (m: string) => foldReliability(t.reliability.filter((r) => r.model_id === m))
  const toggle = (m: string) => setSel((s) => (s.includes(m) ? s.filter((x) => x !== m) : s.length >= 3 ? s : [...s, m]))
  return (
    <Section
      title="Calibration: when an approach says 70%, how often does that team win?"
      help="A calibrated forecaster's 70% calls win about 70% of the time. Points below the diagonal mean the approach was overconfident; above it, underconfident."
    >
      <ul className="mb-3 list-disc pl-5 text-[14px]">
        {avail.map((m) => {
          const v = calibrationVerdict(t.reliability.filter((r) => r.model_id === m), m === 'market_baseline' ? 'The market' : sentenceName(meta, m).replace(/^the /, 'The '))
          return (
            <li key={m} className={v.kind === 'over' || v.kind === 'under' ? '' : 'text-ink-2'}>{v.text}</li>
          )
        })}
      </ul>
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Lines to compare (up to 3)">
        <span className="text-[13px] text-ink-3">Compare up to 3:</span>
        {avail.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={sel.includes(m)}
            onClick={() => toggle(m)}
            className={`rounded-md border px-2 py-0.5 text-[13px] ${sel.includes(m) ? 'border-ink-3 bg-surface-2 text-ink' : 'border-line text-ink-3'}`}
          >
            <ModelBadge modelId={m} />
          </button>
        ))}
      </div>
      <div className="mt-2 h-96 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 384 }}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
            <XAxis type="number" dataKey="mean_p" name="Chance given" domain={[0.5, 1]} tickFormatter={PC} stroke="var(--text-muted)" tick={{ fontSize: 12 }} label={{ value: 'Chance the approach gave the favored team', position: 'insideBottom', offset: -14, fill: 'var(--text-muted)', fontSize: 12 }} />
            <YAxis type="number" dataKey="hit_rate" name="Won" domain={[0.4, 1]} tickFormatter={PC} stroke="var(--text-muted)" tick={{ fontSize: 12 }} width={44} />
            <Tooltip
              cursor={false}
              formatter={(v, name) => [PC(Number(v)), String(name)]}
              contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }}
            />
            <ReferenceLine segment={[{ x: 0.5, y: 0.5 }, { x: 1, y: 1 }]} stroke="var(--text-muted)" strokeDasharray="3 3" ifOverflow="visible" />
            {sel.map((m) => (
              <Scatter key={m} name={label(m)} data={folded(m)} fill={colorVar(m)} stroke={colorVar(m)} line={{ strokeWidth: 2 }} isAnimationActive={false} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[13px] text-ink-2">
        The dotted diagonal is perfect calibration. Each game counts toward the team the approach favored (so a 25% home team is a 75% away team). The highest bins hold few games, so their wobble is mostly noise.
      </p>
      <DataTable summary="Show the numbers: calibration bins">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Line</th>
              <th className={th}>Said</th>
              <th className={th}>Won</th>
              <th className={th}>Games</th>
            </tr>
          </thead>
          <tbody>
            {sel.flatMap((m) =>
              folded(m).map((b) => (
                <tr key={`${m}-${b.mean_p}`}>
                  <td className={td}><ModelBadge modelId={m} /></td>
                  <td className={`${td} tabular`}>{PC(b.mean_p)}</td>
                  <td className={`${td} tabular`}>{PC(b.hit_rate)}</td>
                  <td className={`${td} tabular`}>{b.n.toLocaleString('en-US')}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
