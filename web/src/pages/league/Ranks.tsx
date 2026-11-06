import { useState, type CSSProperties } from 'react'
import { DataTable, td, th } from '../../components/ui'
import type { TeamFeature, TeamsFile } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { firstSort, rankColumns, shadeFor, sortTeams, type RankSort } from './context'
import { fmtValue } from './helpers'

/** Shade with a theme token at an opacity: the accent where a measure has a good direction, the neutral band where it has none. Never a team's brand color. */
const shadeClass = (f: TeamFeature) =>
  f.better == null
    ? 'bg-[color-mix(in_srgb,var(--band-strong)_var(--shade),transparent)]'
    : 'bg-[color-mix(in_srgb,var(--accent)_var(--shade),transparent)]'

function Head({ id, label, sort, onSort, first }: { id: string; label: string; sort: RankSort; onSort: (id: string) => void; first?: boolean }) {
  const on = sort.key === id
  return (
    <th scope="col" aria-sort={on ? sort.dir : 'none'} className={`${th} ${first ? 'sticky left-0 z-[1] bg-surface-1' : 'text-right'} p-0`}>
      <button
        type="button"
        onClick={() => onSort(id)}
        className={`w-full whitespace-nowrap px-2 py-1.5 font-medium uppercase tracking-wide hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] ${first ? 'text-left' : 'text-right'}`}
      >
        {label}
        <span aria-hidden className="ml-1 inline-block w-3 text-ink-2">{on ? (sort.dir === 'ascending' ? '▲' : '▼') : ''}</span>
      </button>
    </th>
  )
}

/**
 * All 32 teams on the preset charts' measures, sortable, shaded by league rank (best darkest). The
 * shade is a second cue: every cell also prints its value and rank. Behind a disclosure; it scrolls inside its own box on a phone.
 */
export function Ranks({ file }: { file: TeamsFile }) {
  const cols = rankColumns(file)
  const [sort, setSort] = useState<RankSort>({ key: 'team', dir: 'ascending' })
  if (cols.length === 0) return null
  const onSort = (id: string) =>
    setSort((cur) => {
      if (cur.key !== id) return firstSort(id, cols.find((c) => c.id === id))
      return { key: id, dir: cur.dir === 'ascending' ? 'descending' : 'ascending' }
    })
  const codes = sortTeams(file, sort)
  return (
    <DataTable summary="Show the ranks">
      <p className="mb-2 text-ink-3">Click a heading to sort. Each cell is the value and the league rank, 1 the best. Darker shading is a better rank; measures with no good or bad direction are shaded by size, highest darkest.</p>
      <table className="w-full border-collapse text-[13px]">
        <caption className="sr-only">Every team on the starting-view measures</caption>
        <thead>
          <tr>
            <Head id="team" label="Team" sort={sort} onSort={onSort} first />
            {cols.map((f) => (
              <Head key={f.id} id={f.id} label={f.short} sort={sort} onSort={onSort} />
            ))}
          </tr>
        </thead>
        <tbody>
          {codes.map((c) => {
            const t = file.teams[c]
            return (
              <tr key={c}>
                <th scope="row" className={`${td} sticky left-0 z-[1] whitespace-nowrap bg-surface-1 text-left font-normal text-ink`}>
                  {teamInfo(c).name || c}
                </th>
                {cols.map((f) => {
                  const rank = t.rank?.[f.id]
                  const shade = shadeFor(rank, f.n)
                  return (
                    <td
                      key={f.id}
                      data-shade={shade ?? undefined}
                      style={shade == null ? undefined : ({ '--shade': `${shade}%` } as CSSProperties)}
                      className={`${td} tabular whitespace-nowrap text-right ${shade == null ? '' : shadeClass(f)}`}
                    >
                      {fmtValue(t.values[f.id], f)}
                      {rank != null && <span className="ml-1 text-ink-3">{rank}</span>}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </DataTable>
  )
}
