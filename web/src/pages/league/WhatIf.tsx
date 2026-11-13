/**
 * The What if mode's controls (M26.4, ADR 0029), laid out across the top so the bracket below keeps the
 * full width: one row of controls, then week chips (or a team picker) and that week's (or team's) games
 * as a grid of small cards. Decide a game by clicking a team; clicking it again leaves it to the source.
 */
import { useState, type CSSProperties } from 'react'
import type { LeagueFile, LeagueGame } from '../../data/contract'
import { kickoffEt, pct } from '../../lib/format'
import type { Source } from '../../lib/league/input'
import { matchupVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { Segmented } from '../../components/ui'
import { gamesByWeek, setTeamGames, teamGames, toggle, type Decided, type Scenario } from './whatif'

const FROM_LABEL: Record<Decided['from'], string> = { link: '', pick: 'your pick', favorite: 'favorite' }

function DecideButton({ team, side, p, on, other, onClick }: { team: string; side: 'away' | 'home'; p: number | null; on: boolean; other: boolean; onClick: () => void }) {
  const c = `var(--team-${side})`
  const style = { '--pick-c': c, background: on ? `color-mix(in srgb, ${c} 30%, var(--surface-1))` : undefined, boxShadow: on ? `inset 0 0 0 2px ${c}` : undefined } as CSSProperties
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={team}
      title={on ? 'Leave this game to the simulation' : `${teamInfo(team).name} win this game${p == null ? '' : ` (${pct(p)} now)`}`}
      onClick={onClick}
      style={style}
      className={`pick-btn inline-flex min-w-0 flex-1 cursor-pointer items-center justify-center gap-1 rounded-md border px-1.5 py-1 text-[13px] font-semibold transition-[background-color,box-shadow,opacity] duration-[var(--dur-fast)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] ${on ? 'pick-pop border-transparent text-ink' : 'border-line text-ink-2 hover:text-ink'} ${other ? 'opacity-55 hover:opacity-100' : ''}`}
    >
      <span aria-hidden className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: c }} />
      {team}
      {p != null && <span aria-hidden className="tabular text-[11px] font-normal text-ink-3">{Math.round(100 * p)}</span>}
    </button>
  )
}

/** One game on one line: the two teams to pick, each with its chance now; the week when listed by team. */
function GameCard({ g, d, source, onPick, week = false }: { g: LeagueGame; d: Decided | undefined; source: Source; onPick: (team: string) => void; week?: boolean }) {
  const p = source === 'student' ? g.p_student : g.p_market
  const won = d ? (d.winner === 'home' ? g.home : g.away) : null
  const tag = d ? FROM_LABEL[d.from] : ''
  return (
    <li data-matchup style={matchupVars(g.away, g.home)} title={`${g.away} at ${g.home}${g.kickoff ? `, ${kickoffEt(g.kickoff)}` : ''}${tag ? ` · ${tag}` : ''}`} className="relative flex min-w-0 items-center gap-1 rounded-md border border-line bg-surface-1 p-1">
      {week && <span className="tabular shrink-0 px-0.5 text-[11px] text-ink-3">{g.week}</span>}
      <span role="group" aria-label={`Decide ${g.away} at ${g.home}`} className="flex min-w-0 flex-1 items-center gap-1">
        <DecideButton team={g.away} side="away" p={p == null ? null : 1 - p} on={won === g.away} other={won === g.home} onClick={() => onPick(g.away)} />
        <span className="text-[10px] text-ink-3">@</span>
        <DecideButton team={g.home} side="home" p={p} on={won === g.home} other={won === g.away} onClick={() => onPick(g.home)} />
      </span>
      {tag && <span className="absolute -top-1.5 right-1 rounded-full border border-line bg-surface-2 px-1 text-[9px] leading-tight text-ink-3">{tag}</span>}
    </li>
  )
}

const GRID = 'm-0 grid list-none grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-1.5 p-0 pt-1'

export function WhatIfPanel({ file, scenario, decided, source, nPicks, onChange }: {
  file: LeagueFile
  scenario: Scenario
  decided: Map<string, Decided>
  source: Source
  nPicks: number
  onChange: (s: Scenario) => void
}) {
  const weeks = gamesByWeek(file)
  const [copied, setCopied] = useState(false)
  const [by, setBy] = useState<'week' | 'team'>('week')
  const [week, setWeek] = useState<number | null>(null)
  const [team, setTeam] = useState('')
  const teams = [...new Set(file.games.flatMap((g) => [g.home, g.away]))].sort((a, b) => teamInfo(a).name.localeCompare(teamInfo(b).name))
  const shownWeek = week ?? weeks[0]?.[0] ?? null
  const copy = () => {
    try {
      void navigator.clipboard?.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // no clipboard: the address bar has the link
    }
  }
  const btn = 'cursor-pointer rounded-md border border-line px-2.5 py-1 text-[13px] text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-default disabled:opacity-50'
  const pickOf = (g: LeagueGame) => (t: string) => onChange(toggle(scenario, g, t, decided.get(g.game_id)))

  let body
  if (by === 'team') {
    const games = team ? teamGames(file, team) : []
    const winner = (g: LeagueGame) => {
      const d = decided.get(g.game_id)
      return d ? (d.winner === 'home' ? g.home : g.away) : null
    }
    const won = games.filter((g) => winner(g) === team).length
    const lost = games.filter((g) => winner(g) && winner(g) !== team).length
    body = (
      <>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-[13px] text-ink-2">
            Team
            <select value={team} onChange={(e) => setTeam(e.target.value)} className="cursor-pointer rounded-md border border-line bg-surface-1 px-2 py-1 text-ink">
              <option value="">Choose a team…</option>
              {teams.map((t) => (
                <option key={t} value={t}>
                  {teamInfo(t).name}
                </option>
              ))}
            </select>
          </label>
          {team && (
            <>
              <button type="button" className={btn} onClick={() => onChange(setTeamGames(scenario, games, team, 'win'))}>{team} wins out</button>
              <button type="button" className={btn} onClick={() => onChange(setTeamGames(scenario, games, team, 'lose'))}>{team} loses out</button>
              <button type="button" className={btn} onClick={() => onChange(setTeamGames(scenario, games, team, 'clear'))}>Clear</button>
              <span className="text-[12px] text-ink-3">{games.length} games left · decided {won}–{lost} for {team}</span>
            </>
          )}
        </div>
        {team && (
          <ul className={GRID}>
            {games.map((g) => <GameCard key={g.game_id} g={g} d={decided.get(g.game_id)} source={source} onPick={pickOf(g)} week />)}
          </ul>
        )}
      </>
    )
  } else {
    const games = weeks.find(([w]) => w === shownWeek)?.[1] ?? []
    body = (
      <>
        <div role="tablist" aria-label="Week" className="flex flex-wrap gap-1">
          {weeks.map(([w, gs]) => {
            const n = gs.filter((g) => decided.has(g.game_id)).length
            const on = w === shownWeek
            return (
              <button
                key={w}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setWeek(w)}
                className={`tabular cursor-pointer rounded-full border px-2.5 py-0.5 text-[12px] ${on ? 'border-[var(--accent)] bg-accent/20 font-medium text-ink' : 'border-line text-ink-2 hover:bg-surface-2'}`}
              >
                Wk {w}
                {n > 0 && <span className={`ml-1 ${n === gs.length ? 'text-[var(--good)]' : 'text-ink-3'}`}>{n === gs.length ? '✓' : `${n}/${gs.length}`}</span>}
              </button>
            )
          })}
        </div>
        <ul className={GRID} aria-label={`Week ${shownWeek} games`}>
          {games.map((g) => <GameCard key={g.game_id} g={g} d={decided.get(g.game_id)} source={source} onPick={pickOf(g)} />)}
        </ul>
      </>
    )
  }

  return (
    <section aria-label="What if: decide games" className="flex flex-col gap-2 rounded-lg border border-line bg-surface-1 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[14px] font-medium text-ink">Decide games</span>
        <Segmented<'week' | 'team'> label="Decide games" value={by} onChange={setBy} options={[{ value: 'week', label: 'By week' }, { value: 'team', label: 'By team' }]} />
        {nPicks > 0 && (
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[13px] text-ink-2 hover:bg-surface-2">
            <input type="checkbox" checked={scenario.usePicks} onChange={(e) => onChange({ ...scenario, usePicks: e.target.checked })} className="cursor-pointer accent-[var(--accent)]" />
            Use my {nPicks} {nPicks === 1 ? 'pick' : 'picks'}
          </label>
        )}
        <button type="button" aria-pressed={scenario.fav} className={`${btn} ${scenario.fav ? 'bg-accent/20 text-ink' : ''}`} onClick={() => onChange({ ...scenario, fav: !scenario.fav })}>
          Favorites win out
        </button>
        <button type="button" className={btn} onClick={() => onChange({ ...scenario, decisions: new Map(), fav: false })} disabled={scenario.decisions.size === 0 && !scenario.fav}>
          Reset
        </button>
        <button type="button" className={btn} onClick={copy}>
          {copied ? 'Link copied' : 'Copy link'}
        </button>
        <span className="text-[12px] text-ink-3 sm:ml-auto">
          {decided.size} of {file.games.length} decided; the rest from the {source === 'student' ? "Student's" : "market's"} chances
        </span>
      </div>
      {body}
    </section>
  )
}
