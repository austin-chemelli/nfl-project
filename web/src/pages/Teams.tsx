import { Link } from 'react-router'
import { TeamAccent } from '../components/TeamAccent'
import { Card, Loaded, Page } from '../components/ui'
import { isNotFound, useTeams } from '../data/api'
import { teamInfo } from '../lib/teams'
import { divisionsOf, recordText } from './league/helpers'

/** Where the nav's Teams item lands: all 32, by division. */
export default function TeamsPage() {
  const q = useTeams()
  return (
    <Page title="Teams" lede="Pick a team to see where it stands, who calls its plays and what to expect from them.">
      {q.isError && isNotFound(q.error) ? <Card className="text-ink-2">The team list appears after the next data update.</Card> : <Loaded q={q} what="teams">
        {(file) => (
          <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
            {divisionsOf(file).map((d) => (
              <section key={d} aria-label={d}>
                <h2 className="mb-1 text-[12px] font-medium uppercase tracking-wide text-ink-3">{d}</h2>
                <ul>
                  {Object.entries(file.teams)
                    .filter(([, t]) => t.division === d)
                    .sort(([, a], [, b]) => b.wins - a.wins || a.losses - b.losses)
                    .map(([code, t]) => (
                      <li key={code} className="border-b border-line">
                        <Link to={`/team/${code}`} className="flex items-baseline gap-2 py-1.5 text-[14px]">
                          <span className="min-w-0 flex-1">
                            <span className="text-ink">{teamInfo(code).name}</span>
                            <TeamAccent team={code} className="mt-0.5 !w-8" />
                          </span>
                          <span className="tabular text-ink-2">{recordText(t)}</span>
                        </Link>
                      </li>
                    ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </Loaded>}
    </Page>
  )
}
