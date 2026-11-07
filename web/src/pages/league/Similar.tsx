import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { FinePrint } from '../../components/FinePrint'
import { Card, ErrorBox, Loading } from '../../components/ui'
import { isNotFound, useSimilar } from '../../data/api'
import type { LeagueFile, SimilarFile, SimilarTeam } from '../../data/contract'
import { TeamLink } from '../../components/TeamLink'
import { teamInfo } from '../../lib/teams'
import { FinishGrid } from './FinishGrid'
import { FlagCards } from './FlagCards'
import { OverlapChart, OverlapKey } from './OverlapChart'
import { poolYears, resolveSimilarTeam, similarOptions, similarRows } from './similar'

const field = 'rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink'
const COLS = 'md:grid-cols-[4.5rem_5rem_8rem_6rem_minmax(0,1fr)]'

function Section({ title, lede, children }: { title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-2">
      <h3 className="text-[15px] font-medium text-ink">{title}</h3>
      {lede && <p className="m-0 text-ink-2">{lede}</p>}
      {children}
    </section>
  )
}

/**
 * The Similar seasons tab: past team-seasons that looked like a team after the same number of games
 * (ADR 0019). Descriptive only; the playoff odds are the forecast. Its data is its own file, so a missing
 * or malformed one only affects this tab.
 */
export function Similar({ file }: { file: LeagueFile }) {
  const q = useSimilar()
  if (q.isPending) return <Loading what="similar seasons" />
  if (q.isError) {
    return isNotFound(q.error) ? <Card className="text-ink-2">Similar seasons appear after the next data update.</Card> : <ErrorBox error={q.error} />
  }
  return <Body file={file} sim={q.data} />
}

function Body({ file, sim }: { file: LeagueFile; sim: SimilarFile }) {
  const [params, setParams] = useSearchParams()
  const [active, setActive] = useState<number | null>(null)
  const team = resolveSimilarTeam(file, sim, params.get('team'))
  const options = similarOptions(file, sim)
  const entry: SimilarTeam | null = team && Object.hasOwn(sim.teams, team) ? sim.teams[team] : null
  const name = team ? teamInfo(team).name || team : ''

  if (Object.keys(sim.teams).length === 0 || !team) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <p className="text-ink-2">
          {(file.through_week ?? 0) < 4 ? 'Similar seasons appear once teams have played four games. They aren\'t in this data yet.' : "Similar seasons aren't available right now."}
        </p>
      </div>
    )
  }

  const rows = entry ? similarRows(entry, sim.measures) : []
  const years = entry ? poolYears(entry.pool) : null
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-col gap-4">
        <p className="m-0 text-ink-2">
          {entry ? `Teams that looked like the ${name} after ${entry.games_played} games finished like this. ` : ''}This describes the past and isn't a forecast; the{' '}
          <Link to={{ search: '?tab=odds' }}>playoff odds</Link> are the forecast.
        </p>
        <p className="m-0 text-[13px]"><TeamLink team={team}>{name} team page</TeamLink></p>

        <label className="flex w-full min-w-0 max-w-xs flex-col gap-0.5 text-[12px] text-ink-3">
          Team
          <select
            value={team}
            onChange={(e) => { setActive(null); setParams((prev) => { const n = new URLSearchParams(prev); n.set('team', e.target.value); return n }, { replace: true, preventScrollReset: true }) }}
            className={`${field} w-full`}
          >
            {options.map((o) => (
              <option key={o.code} value={o.code}>
                {o.name}{o.has ? '' : ' (nothing to show yet)'}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!entry && (
        <p role="status" className="m-0 rounded-lg border border-line bg-surface-1 p-3 text-ink-2">
          {name} has nothing to show yet: it has played fewer than four games, or one of the measures the comparison needs is missing.
        </p>
      )}

      {entry && (
        <>
          <Section
            title={`How the ${entry.nearest.length} nearest seasons finished`}
            lede={
              <>
                {entry.made_playoffs} of {entry.k_summary} made the playoffs and {entry.rounds.conf} reached a conference game or beyond. Each square is one season, furthest round first.
              </>
            }
          >
            <FinishGrid nearest={entry.nearest} active={active} onActive={setActive} />
          </Section>

          <Section title="What history says about this team" lede="Past teams on exactly the same record, split by whether they had the trait. The counts are teams that made the playoffs, or reached a conference game where the card says so.">
            <FlagCards flags={entry.flags} gamesPlayed={entry.games_played} record={entry.record} peers={entry.peers} />
          </Section>

          <Section
            title="Where they overlap"
            lede={`Each row is one measure, as a percentile from 0 to 100 among every team at ${entry.games_played} games since 2002; right is better, except on Schedule, where right is the hardest. The large dot is the ${name}, the small dots are the ${entry.nearest.length} nearest seasons, and the shaded band holds the middle half of them. Where the small dots gather around the large dot, they match. Ranks on the cards above are this season's; these percentiles are across all those seasons.`}
          >
            <OverlapChart code={team} name={name} entry={entry} measures={sim.measures} active={active} onActive={setActive} />
            <OverlapKey code={team} name={name} active={active} near={entry.nearest} />
          </Section>

          <Section title={`The ${rows.length} nearest`}>
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
                  <li
                    key={r.key}
                    tabIndex={0}
                    data-active={active === r.index || undefined}
                    onPointerEnter={(e) => { if (e.pointerType === 'mouse') setActive(r.index) }}
                    onPointerLeave={(e) => { if (e.pointerType === 'mouse') setActive(null) }}
                    onFocus={() => setActive(r.index)}
                    onBlur={() => setActive(null)}
                    onClick={() => setActive(r.index)}
                    className={`grid cursor-default grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-0.5 border-b border-line px-2 py-2 text-[13px] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] data-[active]:bg-surface-2 md:grid-cols-1 md:py-1.5 ${COLS}`}
                  >
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
                    {r.close && <span className="col-start-2 text-[12px] text-ink-3 md:col-span-full md:col-start-1 md:pl-[4.5rem]">{r.close}</span>}
                  </li>
                ))}
              </ol>
            </div>
          </Section>
        </>
      )}

      <FinePrint label="How these seasons are picked">
        <p>
          Every team-season from {years ?? '2002 to 2025'} is compared with {entry ? name : 'the team'} at the same number of games played, not the same week, so a bye doesn't throw it off. Only seasons that played this many games count, so late in a season the pool is
          smaller. Seasons before 2021 had 16 games and later ones have 17, so records like 12-4 and 12-5 sit side by side. The seven measures are: win percentage so far (counted double), points margin per game, a win percentage implied by points scored and allowed,
          offensive efficiency and defensive efficiency adjusted for opponents, the quarterback's efficiency, and strength of schedule. The closest ten are listed and the closest {entry?.k_summary ?? 25} are counted.
        </p>
        <p>
          The cards come from a fixed list of measures, tested on 2002 to 2025 at 6, 8, 10 and 12 games, and show only from 6 to 12 games. A quarter means about a quarter of that season's teams. Each card compares teams on exactly the same record, so it says what
          separated teams at that record, not that a measure matters or doesn't on its own. The list was chosen after looking at those same seasons, and each card pointed the same way in the older and newer halves, but nothing here is a true held-out test. QB play's
          penalty was mostly in the newer half. "Looks bad, wasn't" means no penalty was found, which isn't proof of none. A card is left out when this team's own record doesn't show the pattern, or too few past teams shared it.
        </p>
        <p>
          Before 2020 six teams per conference made the playoffs, and from 2020 seven do, so neighbours from the six-team field had a slightly harder cut to make. The team printed is the one the franchise used then, so a season can appear under a team that has since moved,
          such as SD, which is now the Chargers in Los Angeles. This is a description of what happened to similar teams, and it says nothing about what an injury, a schedule or luck does from here.
        </p>
      </FinePrint>
    </div>
  )
}
