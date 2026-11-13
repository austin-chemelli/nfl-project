import { Link } from 'react-router'
import type { LeagueFile, LeagueGame } from '../../data/contract'
import { kickoffEt, pct } from '../../lib/format'
import { gamesByLeverage, swingLines } from './playoffs'
import { SimFinePrint } from './Odds'

const SHOWN = 3

function GameRow({ g, file }: { g: LeagueGame; file: LeagueFile }) {
  const lines = swingLines(g, file)
  return (
    <li className="border-b border-line py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <Link to={`/game/${g.game_id}`} className="text-[15px] font-medium">
          {g.away} @ {g.home}
        </Link>
        <span className="text-[13px] text-ink-3">
          Week {g.week}
          {g.kickoff && ` · ${kickoffEt(g.kickoff)}`}
          {g.p_market != null && ` · Market ${g.p_market >= 0.5 ? g.home : g.away} ${pct(Math.max(g.p_market, 1 - g.p_market))}`}
          {g.p_student != null && ` · Student ${g.p_student >= 0.5 ? g.home : g.away} ${pct(Math.max(g.p_student, 1 - g.p_student))}`}
        </span>
      </div>
      {lines.length === 0 ? (
        <p className="mt-1 text-[13px] text-ink-3">{Math.min(g.n_home_wins ?? 0, g.n_away_wins ?? 0) < 1000 ? 'Too one-sided to measure what it changes.' : "Little here changes anyone's playoff chances."}</p>
      ) : (
        <ul className="mt-1 list-none p-0 text-[13px] text-ink-2">
          {lines.slice(0, SHOWN).map((l) => (
            <li key={l} className="tabular">
              {l}
            </li>
          ))}
          {lines.length > SHOWN && <li className="text-ink-3">and {lines.length - SHOWN} more</li>}
        </ul>
      )}
    </li>
  )
}

/** The Games that matter tab: the next week's games by how much they move playoff odds, then the rest (ADR 0019). */
export function Games({ file }: { file: LeagueFile }) {
  const { next, rest, week } = gamesByLeverage(file.games)
  if (week == null) return <p className="text-ink-2">No games are left to simulate.</p>
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <p className="text-ink-2">Games that move playoff chances the most, by the market's simulations.</p>
      <section aria-label={`Week ${week} games`}>
        <h3 className="text-[15px] font-medium text-ink">Week {week}</h3>
        <ul className="m-0 list-none p-0">
          {next.map((g) => (
            <GameRow key={g.game_id} g={g} file={file} />
          ))}
        </ul>
      </section>
      {rest.length > 0 && (
        <section aria-label="Later games">
          <h3 className="text-[15px] font-medium text-ink">Biggest games in later weeks</h3>
          <ul className="m-0 list-none p-0">
            {rest.map((g) => (
              <GameRow key={g.game_id} g={g} file={file} />
            ))}
          </ul>
        </section>
      )}
      <SimFinePrint file={file} />
    </div>
  )
}
