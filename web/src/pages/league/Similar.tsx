import { Link, useSearchParams } from 'react-router'
import { FinePrint } from '../../components/FinePrint'
import { StatTile } from '../../components/ui'
import type { LeagueFile } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { resolveSimilarTeam, similarOptions, similarRows, similarTiles } from './context'

const field = 'rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink'
const COLS = 'md:grid-cols-[4.5rem_5rem_8rem_6rem_minmax(0,1fr)]'

/**
 * The Similar seasons tab: past team-seasons that looked like a team after the same number of games
 * (ADR 0019). Descriptive only; the playoff odds are the forecast.
 */
export function Similar({ file }: { file: LeagueFile }) {
  const [params, setParams] = useSearchParams()
  // No team picked: the Student's best chance at the playoffs among teams that have an entry, so the tab opens on something to read.
  const team = resolveSimilarTeam(file, params.get('team'))
  const options = similarOptions(file)
  const entry = team && Object.hasOwn(file.similar, team) ? file.similar[team] : null
  const name = team ? teamInfo(team).name || team : ''

  if (Object.keys(file.similar).length === 0 || !team) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <p className="text-ink-2">Similar seasons appear once teams have played four games. They aren't in this data yet.</p>
      </div>
    )
  }

  const rows = entry ? similarRows(entry) : []
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="text-ink-2">
        {entry ? `Teams that looked like the ${name} after ${entry.games_played} games finished like this.` : 'Teams that looked like the this after a number of games finished like this.'} This describes the past and isn't a forecast; the{' '}
        <Link to={{ search: '?tab=odds' }}>playoff odds</Link> are the forecast.
      </p>

      <label className="flex w-full min-w-0 max-w-xs flex-col gap-0.5 text-[12px] text-ink-3">
        Team
        <select
          value={team}
          onChange={(e) => setParams((prev) => { const n = new URLSearchParams(prev); n.set('team', e.target.value); return n }, { replace: true, preventScrollReset: true })}
          className={`${field} w-full`}
        >
          {options.map((o) => (
            <option key={o.code} value={o.code}>
              {o.name}{o.has ? '' : ' (nothing to show yet)'}
            </option>
          ))}
        </select>
      </label>

      {!entry && (
        <p role="status" className="rounded-lg border border-line bg-surface-1 p-3 text-ink-2">
          {name} has nothing to show yet: it has played fewer than four games, or one of the measures the comparison needs is missing.
        </p>
      )}

      {entry && (
        <>
          <div role="group" aria-label={`The ${entry.k_summary} most similar seasons`} className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
            {similarTiles(entry).map((t, i) => (
              <div key={t.key} className={`[&>div]:h-full ${i === 0 ? 'col-span-2 sm:col-span-1' : ''}`}>
                <StatTile label={t.label} value={t.value} />
              </div>
            ))}
          </div>
          <p className="text-[13px] text-ink-3">Counted over the {entry.k_summary} nearest seasons. The {rows.length} nearest are listed.</p>

          <div>
            <div aria-hidden className={`hidden gap-x-3 border-b border-line px-2 pb-1 text-[12px] uppercase tracking-wide text-ink-3 md:grid ${COLS}`}>
              <span>Season</span>
              <span>Team</span>
              <span>After {entry.games_played} games</span>
              <span>Finished</span>
              <span>Result</span>
            </div>
            <ol aria-label={`Seasons most like ${name}`} className="m-0 list-none p-0">
              {rows.map((r) => (
                <li key={r.key} className={`grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-0.5 border-b border-line px-2 py-2 text-[13px] md:grid-cols-1 md:py-1.5 ${COLS}`}>
                  <span className="tabular font-medium text-ink">{r.season}</span>
                  <span title={teamInfo(r.team).name || undefined} className="text-ink">
                    {r.team}
                  </span>
                  <span className="col-start-2 flex flex-wrap gap-x-3 md:contents">
                    <span className="tabular text-ink-2">
                      <span className="text-ink-3 md:hidden">After {entry.games_played} games </span>
                      {r.then}
                    </span>
                    <span className="tabular text-ink-2">
                      <span className="text-ink-3 md:hidden">Finished </span>
                      {r.final}
                    </span>
                  </span>
                  <span className={`col-start-2 md:col-start-auto ${r.playoffs ? 'text-ink' : 'text-ink-2'}`}>{r.outcome}</span>
                </li>
              ))}
            </ol>
          </div>
        </>
      )}

      <FinePrint label="How these seasons are picked">
        <p>
          Every team-season from 2002 to 2025 is compared with {entry ? name : 'the team'} at the same number of games played, not the same week, so a bye doesn't throw it off. The seven measures are: win percentage so far (counted double), points margin per game, a
          win percentage implied by points scored and allowed, offensive efficiency and defensive efficiency adjusted for opponents, the quarterback's efficiency, and strength of schedule. The closest ten are listed and the closest {entry?.k_summary ?? 25} are counted.
        </p>
        <p>
          Before 2020 six teams per conference made the playoffs, and from 2020 seven do, so a look-alike from the earlier years had a slightly harder cut to make. The team printed is the one the franchise used then, so a season can appear under a team that has since moved,
          such as SD, which is now the Chargers in Los Angeles. This is a description of what happened to similar teams, and it says nothing about what an injury, a schedule or luck does from here.
        </p>
      </FinePrint>
    </div>
  )
}
