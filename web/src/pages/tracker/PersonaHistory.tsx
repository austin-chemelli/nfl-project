import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Help } from '../../components/Help'
import { DataTable, Section, Segmented, td, th } from '../../components/ui'
import type { Meta } from '../../data/contract'
import { colorVar } from '../../lib/models'
import { groupName, helpFor } from '../../lib/meta'
import { calibrationScaleSentence, personaHistoryHeadline } from './helpers'

export function PersonaHistory({ meta }: { meta: Meta }) {
  const apps = meta.approaches
  const [sel, setSel] = useState(apps[0]?.id ?? '')
  const a = apps.find((x) => x.id === sel)
  if (!a) return null
  const P = a.persona_share
  const L = a.public_share
  const H = a.history_share
  const keys = [...new Set([...Object.keys(P), ...Object.keys(L), ...Object.keys(H)])].sort(
    (x, y) => Math.max(Math.abs(P[y] ?? 0), Math.abs(H[y] ?? 0)) - Math.max(Math.abs(P[x] ?? 0), Math.abs(H[x] ?? 0)),
  )
  const data = keys.map((k) => ({ name: groupName(meta, k), persona: P[k] ?? 0, public: L[k] ?? 0, history: H[k] ?? 0 }))
  const head = personaHistoryHeadline(a, (k) => groupName(meta, k))
  const scale = calibrationScaleSentence(a.calibration_scale)
  const color = colorVar(a.id)
  return (
    <Section
      title="What history would change"
      help="Every approach spreads 100 attention points over the same feature groups. The persona chose its split by belief; history's split is what the data alone would choose."
    >
      <p className="mb-3 text-[14px] text-ink-2">
        Each approach has <strong className="text-ink">100 attention points</strong> to spread over the same groups of evidence. For each group: what the persona believes, the public line (the persona after light fitting and calibration, which is what is scored above), and what history alone would choose.
      </p>
      <Segmented label="Approach" value={sel} onChange={setSel} options={apps.map((x) => ({ value: x.id, label: x.name.replace(/^The /, '') }))} />
      <p className="mt-3 italic text-ink-2">{a.blurb}</p>
      {head && <p className="mt-1 font-medium">{head}</p>}
      {scale && <p className="mt-1 text-[13px] text-ink-2">{scale}</p>}
      <div className="mt-3 w-full" style={{ height: 120 + 44 * keys.length }}>
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 400 }}>
          <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" horizontal={false} />
            <XAxis type="number" stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="name" width={104} stroke="var(--text-muted)" tick={{ fontSize: 12 }} interval={0} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)} of 100 points`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="persona" name="Persona believes" fill={color} isAnimationActive={false} />
            <Bar dataKey="public" name="Public line (lightly fitted)" fill={color} fillOpacity={0.55} isAnimationActive={false} />
            <Bar dataKey="history" name="History alone would choose" fill="var(--series-ref)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[13px] text-ink-2">Share of the 100-point attention budget; a negative bar means history says the group points the other way.</p>
      <DataTable summary="Show the numbers: attention points by group">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Group</th>
              <th className={th}>Persona</th>
              <th className={th}>Public line</th>
              <th className={th}>History</th>
              <th className={th}>Why (persona)</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k}>
                <td className={td}><Help text={helpFor(meta, k)}>{groupName(meta, k)}</Help></td>
                <td className={`${td} tabular`}>{(P[k] ?? 0).toFixed(1)}</td>
                <td className={`${td} tabular`}>{(L[k] ?? 0).toFixed(1)}</td>
                <td className={`${td} tabular`}>{(H[k] ?? 0).toFixed(1)}</td>
                <td className={td}>{a.why[k] ?? 'No stated reason (history chose this).'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
