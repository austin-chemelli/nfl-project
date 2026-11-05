import { useState } from 'react'
import { Section, Segmented, TableScroll, td, th } from '../../components/ui'
import type { Meta, Tracker } from '../../data/contract'
import { llVsMarket } from '../../lib/format'
import { APPROACHES, HEADLINE } from '../../lib/models'
import { BUCKET_ORDER, marketWinsWhenApart } from './helpers'
import { label } from './names'

const PC = (v: number | null) => (v == null ? '–' : `${Math.round(100 * v)}%`)

export function Divergence({ t }: { t: Tracker; meta: Meta }) {
  const ids = APPROACHES.filter((m) => t.divergence.some((r) => r.model_id === m))
  const [sel, setSel] = useState<string>(ids.some((m) => m === HEADLINE) ? HEADLINE : ids[0])
  if (!ids.length) return null
  const [wins, total] = marketWinsWhenApart(t.divergence.filter((r) => (ids as string[]).includes(r.model_id)))
  const d = t.divergence.filter((r) => r.model_id === sel).sort((a, b) => BUCKET_ORDER.indexOf(a.bucket) - BUCKET_ORDER.indexOf(b.bucket))
  return (
    <Section
      title="When an approach disagrees with the market"
      help="For each game, the side an approach likes more than the market does. Did that side win more often than the market said it would?"
    >
      {total > 0 && (
        <p className="mb-3 font-medium">
          {wins === total
            ? 'When they disagree by 5+ points, the market has scored better in every approach and every gap.'
            : `When they disagree by 5+ points, the market scored better in ${wins} of ${total} approach-and-gap cases.`}
        </p>
      )}
      <Segmented
        label="Approach"
        value={sel}
        onChange={setSel}
        options={ids.map((m) => ({ value: m, label: label(m) }))}
      />
      <div className="mt-3">
        <TableScroll>
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Disagreement</th>
                <th className={th}>Games</th>
                <th className={th}>Its side won</th>
                <th className={th}>Market expected</th>
                <th className={th}>Log loss vs market</th>
              </tr>
            </thead>
            <tbody>
              {d.map((r) => (
                <tr key={r.bucket}>
                  <td className={td}>{r.bucket} pts</td>
                  <td className={`${td} tabular`}>{r.n.toLocaleString('en-US')}</td>
                  <td className={`${td} tabular`}>
                    {PC(r.lean_win_rate)}
                    {r.lean_win_rate != null && ` (${Math.round(r.lean_win_rate * r.n).toLocaleString('en-US')} of ${r.n.toLocaleString('en-US')})`}
                  </td>
                  <td className={`${td} tabular`}>{PC(r.market_expected_rate)}</td>
                  <td className={`${td} tabular`}>{r.model_log_loss != null && r.market_log_loss != null ? llVsMarket(r.model_log_loss, r.market_log_loss) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      </div>
    </Section>
  )
}
