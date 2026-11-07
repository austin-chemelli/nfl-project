import { Link } from 'react-router'
import type { LeagueFile, TeamFile, TeamsFile } from '../../data/contract'
import { resultText } from '../league/helpers'
import { gameNotes, gamesThatMatter } from './games'

/** Games that matter, then every game of the team (M18.6). `league` and `file` are undefined when those files are missing: what needs them drops. */
export function Games({ code, teams, league, file }: { code: string; teams?: TeamsFile; league?: LeagueFile; file?: TeamFile }) {
  const team = teams?.teams[code]
  const matter = league ? gamesThatMatter(code, league) : []
  if (!team && matter.length === 0) return <p className="m-0 text-ink-2">The schedule appears after the next data update.</p>
  const notes = gameNotes(team?.games ?? [], file)
  return (
    <div className="flex min-w-0 flex-col gap-6 text-[13px]">
      {matter.length > 0 && (
        <section aria-label="Games that matter">
          <h3 className="text-[15px] font-medium text-ink">Games that matter</h3>
          <ul className="m-0 list-none p-0">
            {matter.map(({ game: g, text }) => (
              <li key={g.game_id} className="border-b border-line py-2">
                <Link to={`/game/${g.game_id}`} className="text-[15px] font-medium">
                  {g.away} @ {g.home}
                </Link>
                <span className="text-ink-3"> · Week {g.week}</span>
                <p className="tabular m-0 mt-0.5 text-ink-2">{text}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {team && (
      <section aria-label="Every game">
        <h3 className="text-[15px] font-medium text-ink">Every game</h3>
        <ul className="m-0 grid list-none gap-x-4 p-0 sm:grid-cols-2">
          {team.games.map((g) => {
            const res = resultText(g.pf, g.pa)
            const next = g.id === team.next_game_id
            const note = notes.get(g.id) ?? []
            return (
              <li key={g.id} className="border-b border-line">
                <Link to={`/game/${g.id}`} className="flex items-baseline gap-2 py-1.5">
                  <span className="tabular w-12 shrink-0 whitespace-nowrap text-ink-3">Wk {g.week}</span>{' '}
                  <span className="min-w-0 flex-1 truncate text-ink">
                    {g.home ? 'vs' : '@'} {g.opp}
                  </span>{' '}
                  {res ? <span className="tabular text-ink-2">{res}</span> : next ? <span className="text-ink-2">next</span> : <span className="text-ink-3">–</span>}
                </Link>
                {note.length > 0 && (
                  <ul className="m-0 mb-1.5 list-none p-0 pl-14 text-[12px] text-ink-3">
                    {note.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      </section>
      )}
    </div>
  )
}
