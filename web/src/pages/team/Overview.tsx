import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Help } from '../../components/Help'
import { teamDotVars } from '../../lib/teamColors'
import type { LeagueFile, SimilarFile, TeamsFile } from '../../data/contract'
import { ordinal, fmtValue } from '../league/helpers'
import { FlagCards, HistoryLede } from '../league/FlagCards'
import { fmtProb, winsRange } from '../league/playoffs'
import { Spark } from '../league/Spark'
import { hasSpark } from '../league/context'
import { extremes, pctOf, standing, type Extreme, type Standing } from './overview'

function Section({ title, lede, help, children }: { title: string; lede?: ReactNode; help?: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-2">
      <h3 className="text-[15px] font-medium text-ink">{help ? <Help text={help}>{title}</Help> : title}</h3>
      {lede && <p className="m-0 text-ink-2">{lede}</p>}
      {children}
    </section>
  )
}

function Odd({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-line bg-surface-1 p-3">
      <div className="text-[12px] text-ink-3">{label}</div>
      <div className="tabular text-[20px] font-medium text-ink">{value}</div>
    </div>
  )
}

/** The p10 to p90 wins on a 0 to games-in-season track, with the average as a tick. */
function WinsBand({ lo, hi, mean, total }: { lo: number; hi: number; mean: number; total: number }) {
  const left = pctOf(lo, total)
  const right = pctOf(hi, total)
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
        <span className="text-ink-2">Wins by season's end</span>
        <span className="tabular text-ink">{winsRange({ lo, hi })} <span className="text-ink-3">(average {mean.toFixed(1)})</span></span>
      </div>
      <div role="img" aria-label={`Between ${lo} and ${hi} wins out of ${total} games; average ${mean.toFixed(1)}`} className="relative mt-1.5 h-2 rounded-full bg-[var(--band)]">
        <span className="absolute inset-y-0 rounded-full bg-[var(--band-strong)]" style={{ left: `${left}%`, width: `${Math.max(1.5, right - left)}%` }} />
        <span className="absolute -inset-y-0.5 w-0.5 -translate-x-1/2 rounded bg-[var(--text-secondary)]" style={{ left: `${pctOf(mean, total)}%` }} />
      </div>
      <div className="tabular mt-0.5 flex justify-between text-[11px] text-ink-3">
        <span>0</span>
        <span>{total}</span>
      </div>
    </div>
  )
}

function Stand({ s }: { s: Standing }) {
  const seedText = s.seed ? `Seed ${s.seed} today` : 'Outside the seven playoff seeds today'
  const divText = `${ordinal(s.divRank)} in the division`
  if (!s.odds) {
    const seed = !s.over ? `${seedText}.` : s.seed ? `Finished as seed ${s.seed}.` : 'Out of the playoff seeds.'
    return (
      <p className="m-0 text-ink">
        <span className="tabular font-medium">{s.record}</span>, {divText}. {seed}
      </p>
    )
  }
  const w = s.odds.wins
  return (
    <>
      <p className="m-0 text-ink">
        <span className="tabular font-medium">{s.record}</span>, {divText}. {seedText}.
      </p>
      <div className="grid grid-cols-3 gap-2">
        <Odd label="Playoffs" value={fmtProb(s.odds.playoffs)} />
        <Odd label="Division" value={fmtProb(s.odds.division)} />
        <Odd label="First-round bye" value={fmtProb(s.odds.bye)} />
      </div>
      <WinsBand lo={w.lo} hi={w.hi} mean={w.mean} total={s.total} />
      {hasSpark(s.spark) && (
        <div className="flex items-center gap-3 text-[13px] text-ink-2">
          <Spark points={s.spark} />
          <span className="min-w-0">Playoff chance by week</span>
        </div>
      )}
    </>
  )
}

function ExtremeRow({ e, team }: { e: Extreme; team: TeamsFile['teams'][string] }) {
  const pos = `${Math.min(100, Math.max(0, 100 * e.place))}%`
  return (
    <li className="min-w-0 py-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="min-w-0 text-ink">{e.feature.description ? <Help text={e.feature.description}>{e.feature.label}</Help> : e.feature.label}</span>
        <span className="tabular text-ink-2">
          {fmtValue(team.values[e.feature.id], e.feature)} · <strong className="font-medium text-ink">{ordinal(e.rank)} of {e.of}</strong>
        </span>
      </div>
      <div aria-hidden className="relative mt-1 h-1.5 rounded-full bg-[var(--band)]">
        <span className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ left: pos, background: 'var(--team-home)' }} />
      </div>
    </li>
  )
}

function Group({ title, rows, team }: { title: string; rows: Extreme[]; team: TeamsFile['teams'][string] }) {
  if (rows.length === 0) return null
  return (
    <div className="min-w-0">
      <h4 className="mb-0.5 text-[12px] font-medium uppercase tracking-wide text-ink-3">{title}</h4>
      <ul aria-label={title} className="m-0 list-none p-0">
        {rows.map((e) => <ExtremeRow key={e.feature.id} e={e} team={team} />)}
      </ul>
    </div>
  )
}

/** M18.3. `league` and `similar` are undefined when those files are missing: their sections drop. */
export function Overview({ code, teams, league, similar }: { code: string; teams?: TeamsFile; league?: LeagueFile; similar?: SimilarFile }) {
  const stand = league ? standing(league, code) : null
  const team = teams && Object.hasOwn(teams.teams, code) ? teams.teams[code] : undefined
  const ex = teams ? extremes(teams, code) : null
  const entry = similar && Object.hasOwn(similar.teams, code) ? similar.teams[code] : undefined
  return (
    <div data-matchup style={teamDotVars(code)} className="flex min-w-0 flex-col gap-6">
      {league && stand && (
        <Section title="Where they stand" lede={stand.over ? 'The regular season is over.' : undefined} help={stand.over ? undefined : 'The odds come from playing out the rest of the season many times.'}>
          <Stand s={stand} />
        </Section>
      )}
      {team && ex && (ex.best.length > 0 || ex.worst.length > 0) && (
        <Section
          title="Best and worst"
          lede={`Ranks among ${[...ex.best, ...ex.worst][0].of} teams going into Week ${teams?.week}.`}
          help="Model inputs where more or less is clearly better. Early in the season they lean on last season, so they can differ from the results so far."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <Group title="Best" rows={ex.best} team={team} />
            <Group title="Worst" rows={ex.worst} team={team} />
          </div>
        </Section>
      )}
      {entry && (
        <Section title="History says" lede={<HistoryLede />}>
          <FlagCards flags={entry.flags} gamesPlayed={entry.games_played} record={entry.record} peers={entry.peers} />
          <p className="m-0">
            <Link to={`/league?tab=similar&team=${code}`}>See the similar seasons</Link>
          </p>
        </Section>
      )}
    </div>
  )
}
