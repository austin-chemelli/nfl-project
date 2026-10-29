import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DataTable, Section, Segmented, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { colorVar } from '../../lib/models'
import { BUCKET_ORDER, divergenceSentence, marketWinsWhenApart } from './helpers'
import { label, sentenceName } from './names'

const PC = (v: number | null) => (v == null ? '–' : `${Math.round(100 * v)}%`)

export function Divergence({ t, meta }: { t: Tracker; meta: Meta }) {
  const ids = ['traditionalist', 'analyst', 'sharp', 'student', 'ensemble'].filter((m) => t.divergence.some((r) => r.model_id === m))
  const [sel, setSel] = useState(ids[0])
  if (!ids.length) return null
  const [wins, total] = marketWinsWhenApart(t.divergence.filter((r) => ids.includes(r.model_id)))
  const d = t.divergence.filter((r) => r.model_id === sel).sort((a, b) => BUCKET_ORDER.indexOf(a.bucket) - BUCKET_ORDER.indexOf(b.bucket))
  const bars = d.map((r) => ({
    name: `${r.bucket} pts apart`,
    n: r.n,
    market: r.market_expected_rate,
    side: r.lean_win_rate,
  }))
  return (
    <Section
      title="When an approach disagrees with the market"
      help="For each game, the side an approach likes more than the market does. Did that side win more often than the market said it would?"
    >
      {total > 0 && (
        <p className="mb-3 font-medium">
          {wins === total
            ? 'The market has been right more often when they disagree. In every approach, in every case where the gap was 5+ points, the market\'s probabilities scored better than the approach\'s on those games.'
            : `When they disagree by 5+ points, the market scored better in ${wins} of ${total} approach-and-gap cases.`}
        </p>
      )}
      <Segmented
        label="Approach"
        value={sel}
        onChange={setSel}
        options={ids.map((m) => ({ value: m, label: label(m) }))}
      />
      <ul className="mt-3 list-disc pl-5 text-[14px]">
        {d.map((r) => (
          <li key={r.bucket}>{divergenceSentence(r, sentenceName(meta, sel))}</li>
        ))}
      </ul>
      <div className="mt-3 h-72 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 288 }}>
          <BarChart data={bars} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" vertical={false} />
            <XAxis dataKey="name" stroke="var(--text-muted)" tick={{ fontSize: 12 }} tickFormatter={(v: string, i: number) => `${v} (n = ${bars[i]?.n.toLocaleString('en-US')})`} interval={0} />
            <YAxis domain={[0, 0.6]} tickFormatter={(v: number) => `${Math.round(100 * v)}%`} stroke="var(--text-muted)" tick={{ fontSize: 12 }} width={40} />
            <Tooltip formatter={(v) => PC(Number(v))} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="market" name="Market expected" fill={colorVar('market_baseline')} isAnimationActive={false} />
            <Bar dataKey="side" name={`${label(sel)}'s side won`} fill={colorVar(sel)} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[13px] text-ink-2">
        If an approach saw something the market missed, its bar would sit above the market&apos;s. The side an approach leans toward is the underdog relative to the market, so bars below 50% are expected; what matters is the gap between the two bars.
      </p>
      <DataTable summary="Show the numbers: disagreement buckets">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Gap</th>
              <th className={th}>Games</th>
              <th className={th}>Its side won</th>
              <th className={th}>Market expected</th>
              <th className={th}>Its log loss</th>
              <th className={th}>Market log loss</th>
            </tr>
          </thead>
          <tbody>
            {d.map((r) => (
              <tr key={r.bucket}>
                <td className={td}>{r.bucket} pts</td>
                <td className={`${td} tabular`}>{r.n.toLocaleString('en-US')}</td>
                <td className={`${td} tabular`}>{PC(r.lean_win_rate)}</td>
                <td className={`${td} tabular`}>{PC(r.market_expected_rate)}</td>
                <td className={`${td} tabular`}>{r.model_log_loss?.toFixed(3) ?? '–'}</td>
                <td className={`${td} tabular`}>{r.market_log_loss?.toFixed(3) ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
