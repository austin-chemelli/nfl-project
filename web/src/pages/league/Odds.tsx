import { useMemo, type HTMLAttributes } from 'react'
import { useSearchParams } from 'react-router'
import { TipNote, TipRow, TipTitle, useChartTip } from '../../charts'
import { FinePrint } from '../../components/FinePrint'
import { DataTable, Segmented, td, th } from '../../components/ui'
import type { LeagueFile } from '../../data/contract'
import { dash, kickoffEt } from '../../lib/format'
import { teamDotVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { hasSpark, sparkSeries } from './context'
import { Spark } from './Spark'
import { barWidth, fmtProb, oddsRows, parseConf, parseView, recordOf, marketNote, sourcesText, winsRange, type Conf, type View } from './playoffs'
import { TeamLink } from '../../components/TeamLink'
import { simInputFrom } from '../../lib/league/input'
import { usePicks } from '../../lib/picks'
import { decide, movers, parseScenario, picksInPlay, toOddsTeam, winners, writeScenario, type Scenario } from './whatif'
import { RUNS, useWhatIf } from './useWhatIf'
import { WhatIfPanel } from './WhatIf'
import type { LeagueOddsTeam } from '../../data/contract'

const MAX_WINS = 17
const ROUNDS = [
  ['div', 'Reach the divisional round'],
  ['conf', 'Reach the conference game'],
  ['sb', 'Reach the Super Bowl'],
  ['champ', 'Win the Super Bowl'],
] as const

/** The fine print for the playoff tabs: what each variant used and what the simulation leaves out. */
export function SimFinePrint({ file, whatIf = false }: { file: LeagueFile; whatIf?: boolean }) {
  return (
    <FinePrint label="How these odds are made">
      {whatIf && (
        <p>
          What if: your browser reruns the same simulation with the games you decided fixed, and "now" with nothing fixed, on the same random draws, so the difference is your decisions and not noise. Its "now" can
          differ from the published odds by a point or so, because they are separate samples. Your saved picks count as decisions while "Use my picks" is on; a game you set in the link beats your pick. Beyond the next
          week or so, the market's chances are our estimate of the market, not a quote.
        </p>
      )}
      <p>
        Each team's odds come from {file.n_sims.toLocaleString('en-US')} simulations of the rest of the season, run twice. The Student's run used {sourcesText(file.odds.student)}. The market's run used{' '}
        {sourcesText(file.odds.market)}.
        {(file.odds.market.sources.ratings ?? 0) > 0 && " Tested on 29 lines it hadn't seen in November 2026, that estimate missed by about 7 points of win chance a game and the Student by about 6, so a gap between the two views beyond the next week or so is weak evidence of anything."}
      </p>
      <p>
        Each run moves every team's strength up or down a little for all of that team's games, so a team that is better than rated is better all season. The size was tuned on past seasons, and for the Student the gain
        was too small to tell from noise.
      </p>
      <p>
        Simulated ties in the standings use the real tiebreakers through strength of schedule, then a coin. That procedure matched the real playoff field in all 48 conference-seasons from 2002 to 2025, and no real tie
        went past strength of victory. Today's seeds use the points steps too. Simulated games never end in a tie, and injuries beyond this week are mostly assumed average.
      </p>
      <p>A swing compares the runs where a team won with the runs where it lost, so it includes what a win says about how good that team is in that run, not only the win itself.</p>
      <p>These are simulations, not a count of exact playoff scenarios, so no team is ever shown as certain or out.</p>
    </FinePrint>
  )
}

/** Wins from p10 to p90 on a shared 0 to 17 scale, with the mean as a tick. The page-wide scale is why this isn't a RangeRow, which scales each row to itself. */
function WinsRange({ w }: { w: { mean: number; lo: number; hi: number } }) {
  const at = (v: number) => `${(100 * Math.min(MAX_WINS, Math.max(0, v))) / MAX_WINS}%`
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden className="relative h-2.5 w-24 shrink-0 rounded-sm bg-surface-2 md:w-28">
        <span className="absolute inset-y-0 rounded-sm bg-[var(--band-strong)]" style={{ left: at(w.lo), width: `calc(${at(w.hi)} - ${at(w.lo)} + 2px)` }} />
        <span className="absolute -inset-y-0.5 w-0.5 bg-[var(--text-muted)]" style={{ left: at(w.mean) }} />
      </span>
      <span className="tabular whitespace-nowrap text-ink-2">{winsRange(w)} wins</span>
    </span>
  )
}

/** Below this change (probability) a what-if cell shows no arrow. */
const MOVE_MIN = 0.01

/** "▲23" / "▼8" points of probability, or nothing for a change under a point. */
function Move({ from, to, big = false }: { from: number; to: number; big?: boolean }) {
  const d = to - from
  if (Math.abs(d) < MOVE_MIN) return big ? <span aria-hidden className="w-9 shrink-0" /> : null
  const up = d > 0
  return (
    <span
      title={`${fmtProb(from)} now`}
      aria-label={`${up ? 'up' : 'down'} from ${fmtProb(from)}`}
      className={`tabular shrink-0 text-[11px] font-semibold ${big ? 'w-9 text-left' : 'ml-1'}`}
      style={{ color: up ? 'var(--good)' : 'var(--critical)' }}
    >
      {up ? '▲' : '▼'}
      {Math.round(Math.abs(d) * 100)}
    </span>
  )
}

/** The Playoff odds tab: P(playoffs) for one conference, Student or market (ADR 0019); with `?whatif=1`, your scenario against now (M26.4). */
export function Odds({ file, runs = RUNS }: { file: LeagueFile; runs?: { quick: number; full: number } }) {
  const [params, setParams] = useSearchParams()
  const conf = parseConf(params.get('conf'))
  const view = parseView(params.get('view'))
  const set = (k: string, v: string, fallback: string) =>
    setParams((prev) => { const n = new URLSearchParams(prev); if (v === fallback) n.delete(k); else n.set(k, v); return n }, { replace: true, preventScrollReset: true })
  const scenario = parseScenario(params)
  const canWhatIf = useMemo(() => simInputFrom(file, view) != null, [file, view])
  const on = scenario.on && canWhatIf
  const picks = usePicks()
  const decided = useMemo(() => (on ? decide(file, scenario, picks, view) : new Map()), [on, file, params, picks, view]) // eslint-disable-line react-hooks/exhaustive-deps
  const wi = useWhatIf(file, view, winners(decided), on, runs)
  const setScenario = (sc: Scenario) => setParams((prev) => writeScenario(prev, sc), { replace: true, preventScrollReset: true })

  const base = oddsRows(file, conf, view)
  const live = on && wi.now && wi.next
  const rows: { team: (typeof base)[number]['team']; odds: LeagueOddsTeam; was?: LeagueOddsTeam }[] = live
    ? base.map((r) => ({ team: r.team, odds: toOddsTeam(wi.next![r.team.team]), was: toOddsTeam(wi.now![r.team.team]) })).sort((a, b) => b.odds.playoffs - a.odds.playoffs || a.team.team.localeCompare(b.team.team))
    : base
  const moved = live ? movers(wi.now!, wi.next!, base.map((r) => r.team.team)).slice(0, 4) : []
  const { box, at, bind, card } = useChartTip()
  const anySpark = !on && rows.some((r) => hasSpark(sparkSeries(file, r.team.team, view)))
  const tipRow = rows.find((r) => r.team.team === at?.key)
  if (Object.keys(file.odds.student.teams).length === 0) return <p className="text-ink-2">The regular season is over. The final records are on the Standings tab.</p>

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="text-ink-2">Each team's chance of reaching the playoffs, the top seven in its conference.</p>
      <p className="text-[13px] text-ink-3">Simulated {kickoffEt(file.as_of)}.</p>
      <div className="flex flex-wrap items-center gap-3">
        <Segmented<Conf> label="Conference" value={conf} onChange={(v) => set('conf', v, 'AFC')} options={[{ value: 'AFC', label: 'AFC' }, { value: 'NFC', label: 'NFC' }]} />
        <Segmented<View> label="Odds from" value={view} onChange={(v) => set('view', v, 'student')} options={[{ value: 'student', label: 'Student' }, { value: 'market', label: 'Market' }]} />
        {canWhatIf && (
          <Segmented<'off' | 'on'> label="What if" value={on ? 'on' : 'off'} onChange={(v) => setScenario({ ...scenario, on: v === 'on' })} options={[{ value: 'off', label: 'Published' }, { value: 'on', label: 'What if…' }]} />
        )}
      </div>

      <div className={on ? 'grid items-start gap-4 lg:grid-cols-[21rem_minmax(0,1fr)]' : 'contents'}>
      {on && (
        <div className="lg:sticky lg:top-14 lg:max-h-[calc(100vh-4.5rem)] lg:overflow-y-auto">
          <WhatIfPanel file={file} scenario={scenario} decided={decided} source={view} nPicks={picksInPlay(file, picks)} onChange={setScenario} />
        </div>
      )}
      <div className={on ? 'flex min-w-0 flex-col gap-4' : 'contents'}>
      {on && (
        <div className="flex flex-col gap-1 rounded-md border-l-4 border-[var(--accent)] bg-surface-2 px-3 py-2 text-[13px]" aria-live="polite">
          <span className="font-medium text-ink">
            Your scenario, not the published odds{wi.busy ? ' · simulating…' : wi.runs ? ` · ${wi.runs.toLocaleString('en-US')} simulated seasons` : ''}
          </span>
          {live && (moved.length ? (
            <span className="tabular text-ink-2">
              Biggest movers: {moved.map((m) => `${m.team} ${fmtProb(m.from)} → ${fmtProb(m.to)}`).join(' · ')}
            </span>
          ) : (
            <span className="text-ink-3">{decided.size ? `No ${conf} team moves 3 points or more.` : 'Decide a game below to see who it moves.'}</span>
          ))}
        </div>
      )}

      {view === 'market' && marketNote(file.odds.market) && <p className="text-[13px] text-ink-3">{marketNote(file.odds.market)}</p>}

      <div ref={box} className="relative">
        <div aria-hidden className={`hidden ${on ? 'grid-cols-[5.5rem_2.5rem_minmax(0,1fr)_4.75rem_4.75rem_13rem]' : 'grid-cols-[6.5rem_2.5rem_minmax(0,1fr)_4rem_4rem_13rem]'} gap-x-3 border-b border-line px-2 pb-1 text-[12px] uppercase tracking-wide text-ink-3 md:grid`}>
          <span>Team</span>
          <span>Seed</span>
          <span>Playoffs</span>
          <span className="text-right">Division</span>
          <span className="text-right">Bye</span>
          <span>Wins, p10 to p90</span>
        </div>
        <ol aria-label={`${conf} playoff odds`} className="m-0 list-none p-0">
          {rows.map(({ team, odds, was: rowWas }, i) => (
            <li
              key={team.team}
              data-team={team.team}
              {...(bind(team.team) as unknown as HTMLAttributes<HTMLLIElement>)}
              data-matchup
              style={{ ...teamDotVars(team.team), cursor: 'pointer' }}
              className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-b border-line px-2 py-2 text-[13px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] ${on ? 'md:grid-cols-[5.5rem_2.5rem_minmax(0,1fr)_4.75rem_4.75rem_13rem]' : 'md:grid-cols-[6.5rem_2.5rem_minmax(0,1fr)_4rem_4rem_13rem]'} md:py-1.5 ${i === 7 ? 'border-t-2 border-t-[var(--text-muted)]' : ''}`}
            >
              <span className="order-1 col-span-2 flex items-center gap-2 md:order-3 md:col-span-1">
                <span className="relative h-3 min-w-0 flex-1 rounded-sm bg-surface-2">
                  <span className="absolute inset-y-0 left-0 origin-left rounded-sm transition-[width] duration-[var(--dur-slow)] ease-[var(--ease-out)]" style={{ width: barWidth(odds.playoffs), background: 'var(--team-home)' }} />
                  {rowWas && <span aria-hidden title={`${fmtProb(rowWas.playoffs)} now`} className="absolute -inset-y-0.5 w-0.5 bg-[var(--text-muted)]" style={{ left: barWidth(rowWas.playoffs) }} />}
                </span>
                <span className="tabular w-14 shrink-0 text-right text-[15px] font-semibold text-ink">{fmtProb(odds.playoffs)}</span>
                {on && (rowWas ? <Move from={rowWas.playoffs} to={odds.playoffs} big /> : <span aria-hidden className="w-9 shrink-0" />)}
                {/* when any team has a line, the rest keep its width so every bar stays on one scale */}
                {anySpark && (hasSpark(sparkSeries(file, team.team, view)) ? <Spark points={sparkSeries(file, team.team, view)} /> : <span aria-hidden className="w-16 shrink-0" />)}
              </span>
              <span className="order-2 flex items-baseline gap-2 md:order-1" title={teamInfo(team.team).name}>
                <span onClick={(e) => e.stopPropagation()}><TeamLink team={team.team} className="font-medium">{team.team}</TeamLink></span>
                <span className="tabular whitespace-nowrap text-ink-3">{recordOf(team)}</span>
              </span>
              <span className="tabular order-3 text-right text-ink-2 md:order-2 md:text-left">
                <span className="md:hidden">Seed today </span>
                {team.seed_today ?? dash}
              </span>
              <span className="tabular order-4 text-ink-2 md:order-4 md:text-right">
                <span className="text-ink-3 md:hidden">Division </span>
                {fmtProb(odds.division)}
                {rowWas && <Move from={rowWas.division} to={odds.division} />}
              </span>
              <span className="tabular order-5 text-right text-ink-2 md:text-right">
                <span className="text-ink-3 md:hidden">Bye </span>
                {fmtProb(odds.bye)}
                {rowWas && <Move from={rowWas.bye} to={odds.bye} />}
              </span>
              <span className="order-6 col-span-2 md:col-span-1">
                <WinsRange w={odds.wins} />
              </span>
            </li>
          ))}
        </ol>
        {card(
          tipRow && (
            <>
              <TipTitle note={`${tipRow.team.div} · ${recordOf(tipRow.team)}`}>{teamInfo(tipRow.team.team).name}</TipTitle>
              {ROUNDS.map(([k, label]) => (
                <TipRow key={k} value={fmtProb(tipRow.odds.rounds[k])} label={label} />
              ))}
              <TipNote>{on ? 'Your scenario' : `${view === 'student' ? 'The Student' : 'The market'}'s simulations`}</TipNote>
            </>
          ),
        )}
      </div>
      <p className="text-[13px] text-ink-3">
        The line marks the seven highest chances, not today's seeds. Tap a team for each round.{anySpark && ' Small line: chance at each Tuesday refresh.'}
        {on && ' Gray tick and arrows: the chance now, before your decisions.'}
      </p>
      </div>
      </div>

      <DataTable>
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr>
              <th className={th}>Team</th>
              <th className={`${th} text-right`}>Playoffs</th>
              <th className={`${th} text-right`}>Division</th>
              <th className={`${th} text-right`}>Bye</th>
              {ROUNDS.map(([k, label]) => (
                <th key={k} className={`${th} text-right`}>{label.replace('Reach the ', '').replace('Win the ', 'Win ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ team, odds }) => (
              <tr key={team.team}>
                <td className={td}>{teamInfo(team.team).name}</td>
                <td className={`${td} tabular text-right`}>{fmtProb(odds.playoffs)}</td>
                <td className={`${td} tabular text-right`}>{fmtProb(odds.division)}</td>
                <td className={`${td} tabular text-right`}>{fmtProb(odds.bye)}</td>
                {ROUNDS.map(([k]) => (
                  <td key={k} className={`${td} tabular text-right`}>{fmtProb(odds.rounds[k])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
      <SimFinePrint file={file} whatIf={on} />
    </div>
  )
}
