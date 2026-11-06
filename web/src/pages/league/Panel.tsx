import { Link } from 'react-router'
import type { TeamRow } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { recordText, resultText } from './helpers'

/** The selected team: record, every game linking to its page, the next one marked, the scheme profile. */
export function Panel({ code, team, week, onClose }: { code: string; team: TeamRow; week: number; onClose: () => void }) {
  const nextId = team.next_game_id ?? team.games.find((g) => g.pf == null)?.id ?? null
  return (
    <section aria-label={`${teamInfo(code).name} games`} className="mt-4 rounded-lg border border-line bg-surface-1 p-3 text-[13px]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-medium text-ink">{teamInfo(code).name}</h3>
          <p className="text-ink-2">
            {team.division} · {recordText(team)} · through Week {week - 1}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close team panel" className="shrink-0 rounded px-2 py-1 text-ink-2 hover:text-ink">
          ✕
        </button>
      </div>
      <ul className="mt-2 grid gap-x-4 sm:grid-cols-2">
        {team.games.map((g) => {
          const res = resultText(g.pf, g.pa)
          const next = g.id === nextId
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
      <p className="mt-2">
        <Link to={`/coaches?team=${code}`}>Scheme profile</Link>
      </p>
    </section>
  )
}
