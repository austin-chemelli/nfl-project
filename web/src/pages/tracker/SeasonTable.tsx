import { useMemo } from 'react'
import { DataTable, ModelBadge, td, th } from '../../components/ui'
import type { Tracker } from '../../data/contract'
import { APPROACHES, REFERENCES } from '../../lib/models'

/** Log loss by season, one column per line (the scoring rule is always read against the Market column). */
export function SeasonTable({ t }: { t: Tracker }) {
  const { seasons, cols, cell } = useMemo(() => {
    const cell = new Map<string, number>()
    for (const r of t.seasons) cell.set(`${r.season}|${r.model_id}`, r.log_loss)
    const seasons = [...new Set(t.seasons.map((r) => r.season))].sort((a, b) => b - a)
    const present = new Set(t.seasons.map((r) => r.model_id))
    const cols = ['market_baseline', ...APPROACHES, ...REFERENCES].filter((m, i, a) => a.indexOf(m) === i && present.has(m))
    return { seasons, cols, cell }
  }, [t.seasons])
  if (!seasons.length) return null
  return (
    <>
      <DataTable summary="Show the numbers: log loss by season">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Season</th>
              {cols.map((m) => (
                <th key={m} className={th}><ModelBadge modelId={m} /></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {seasons.map((s) => (
              <tr key={s}>
                <td className={td}>{s}</td>
                {cols.map((m) => (
                  <td key={m} className={`${td} tabular`}>{cell.get(`${s}|${m}`)?.toFixed(3) ?? '–'}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </>
  )
}
