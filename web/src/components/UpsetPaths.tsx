/**
 * How the underdog wins (ADR 0028, M25): the conditions winning underdogs of this size met, each with
 * what history says, how often this dog has done it and this favourite has allowed it. Context, never
 * a forecast: no probability for the upset appears here, and every number is read from the JSON.
 * Finished games add a check per condition. Colour is the dog's, through `[data-matchup]`.
 */
import type { PathsOutcome, UpsetPaths as Paths } from '../data/contract'
import { matchupVars } from '../lib/teamColors'
import { Help } from './Help'

const sizeLabel = (n: number) => (n > 0 ? `+${n}` : String(n))

export function UpsetPaths({ paths, outcome }: { paths: Paths | null; outcome?: PathsOutcome | null }) {
  if (!paths) return null
  const met = new Map((outcome?.conditions ?? []).map((c) => [c.id, c.met]))
  return (
    <section className="mt-8" data-testid="upset-paths" data-matchup style={matchupVars(paths.dog, paths.favorite)}>
      <h3 className="m-0 border-l-[3px] pl-2 text-[15px] font-semibold leading-tight" style={{ borderColor: 'var(--team-away)' }}>
        How {paths.dog} wins <span className="tabular font-normal text-ink-2">{sizeLabel(paths.size)}</span>
      </h3>
      {paths.base_rate_pct != null && (
        <p className="mb-3 mt-1 max-w-3xl text-[13px] text-ink-2">
          Underdogs of this size won {paths.base_rate_pct}% of games (2006–2025).
        </p>
      )}
      <ul className="m-0 flex list-none flex-col p-0">
        {paths.conditions.map((c) => {
          const top = paths.top.includes(c.id)
          const m = met.get(c.id)
          return (
            <li
              key={c.id}
              data-top={top ? '' : undefined}
              className={`flex flex-wrap items-baseline gap-x-4 gap-y-0.5 border-b border-line py-2 ${top ? 'font-semibold' : 'text-ink-2'}`}
            >
              {outcome && (
                <span
                  role="img"
                  aria-label={m ? 'met' : 'not met'}
                  data-met={m ? 'yes' : 'no'}
                  className={`w-4 shrink-0 text-center ${m ? 'text-ink' : 'text-ink-3'}`}
                >
                  {m ? '✓' : '–'}
                </span>
              )}
              <span className="min-w-0 flex-1 basis-48 text-[14px] text-ink">
                <Help text={c.help}>{c.label}</Help>
                <span className="ml-2 inline-block whitespace-nowrap rounded border border-line px-1.5 text-[11px] font-normal text-ink-2">{c.plausibility.replace(/ for every team$/, '')}</span>
              </span>
              <span className="tabular text-[13px] font-normal text-ink-2">
                {c.win_rate_pct != null ? `${c.win_rate_pct}%` : '–'} <span className="text-ink-3">(n {c.n})</span>
              </span>
              <span className="tabular text-[13px] font-normal text-ink-2">
                {paths.dog}: {c.dog_games ? `${c.dog_count} of ${c.dog_games}` : 'no games yet'}
              </span>
              <span className="tabular text-[13px] font-normal text-ink-2">
                {paths.favorite} allowed: {c.fav_games ? `${c.fav_count} of ${c.fav_games}` : 'no games yet'}
              </span>
            </li>
          )
        })}
      </ul>
      <p className="mb-0 mt-3 max-w-3xl text-[13px] text-ink-2">{paths.sentence}</p>
      {outcome && <p className="mb-0 mt-2 max-w-3xl text-[13px] text-ink" data-testid="paths-outcome">{outcome.sentence}</p>}
    </section>
  )
}
