import { useId, type Ref } from 'react'
import { Link } from 'react-router'
import type { TeamRow } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { recordText, resultText } from './helpers'
import { isHidden } from '../../lib/hiddenPages'

/** The selected team: record, every game linking to its page, the next one marked, the scheme profile. */
export function Panel({ code, team, onClose, ref, compare, compareRef }: {
  code: string
  team: TeamRow
  onClose: () => void
  ref?: Ref<HTMLElement>
  /** The compare select, so the page can return focus to it. */
  compareRef?: Ref<HTMLSelectElement>
  /** The "Compare" control: the other teams to pick from and the one picked (null for none). Omitted, no control. */
  compare?: { options: { code: string; name: string }[]; value: string | null; onChange: (code: string | null) => void }
}) {
  const compareId = useId()
  return (
    <section ref={ref} tabIndex={-1} aria-label={`${teamInfo(code).name} games`} className="mt-4 rounded-lg border border-line bg-surface-1 p-3 text-[13px] outline-none">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-medium text-ink">{teamInfo(code).name}</h3>
          <p className="text-ink-2">
            {team.division} · {recordText(team)}
            {team.through_week != null && ` · through Week ${team.through_week}`}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close team panel" className="shrink-0 rounded px-2 py-1 text-ink-2 hover:text-ink">
          ✕
        </button>
      </div>
      {compare && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label htmlFor={compareId} className="text-ink-3">
            Compare with
          </label>
          <select
            ref={compareRef}
            id={compareId}
            value={compare.value ?? ''}
            onChange={(e) => compare.onChange(e.target.value || null)}
            className="max-w-full rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink"
          >
            <option value="">No team</option>
            {compare.options.map((o) => (
              <option key={o.code} value={o.code}>
                {o.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <ul className="mt-2 grid gap-x-4 sm:grid-cols-2">
        {team.games.map((g) => {
          const res = resultText(g.pf, g.pa)
          const next = g.id === team.next_game_id
          return (
            <li key={g.id} className="border-b border-line">
              <Link to={`/game/${g.id}`} className="flex items-baseline gap-2 py-1.5">
                <span className="tabular w-12 shrink-0 whitespace-nowrap text-ink-3">Wk {g.week}</span>{' '}
                <span className="min-w-0 flex-1 truncate text-ink">
                  {g.home ? 'vs' : '@'} {g.opp}
                </span>{' '}
                {res ? <span className="tabular text-ink-2">{res}</span> : next ? <span className="text-ink-2">next</span> : <span className="text-ink-3">–</span>}
              </Link>
            </li>
          )
        })}
      </ul>
      {!isHidden('/coaches') && (
        <p className="mt-2">
          <Link to={`/coaches?team=${code}`}>Scheme profile</Link>
        </p>
      )}
    </section>
  )
}
