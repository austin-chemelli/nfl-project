/** The What if mode's controls and game list (M26.4, ADR 0029): decide games, use your picks, favorites win out, reset, copy the link. */
import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router'
import type { LeagueFile, LeagueGame } from '../../data/contract'
import { kickoffEt, pct } from '../../lib/format'
import type { Source } from '../../lib/league/input'
import { matchupVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { gamesByWeek, toggle, type Decided, type Scenario } from './whatif'

const FROM_LABEL: Record<Decided['from'], string> = { link: 'decided', pick: 'your pick', favorite: 'favorite' }

function DecideButton({ team, side, on, other, onClick }: { team: string; side: 'away' | 'home'; on: boolean; other: boolean; onClick: () => void }) {
  const c = `var(--team-${side})`
  const style = { '--pick-c': c, background: on ? `color-mix(in srgb, ${c} 30%, var(--surface-1))` : undefined, boxShadow: on ? `inset 0 0 0 2px ${c}` : undefined } as CSSProperties
  return (
    <button
      type="button"
      aria-pressed={on}
      title={on ? `Leave this game to the simulation` : `${teamInfo(team).name} win this game`}
      onClick={onClick}
      style={style}
      className={`pick-btn inline-flex min-w-14 cursor-pointer items-center justify-center gap-1 rounded-md border px-2.5 py-1 text-[13px] font-semibold transition-[background-color,box-shadow,opacity] duration-[var(--dur-fast)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] ${on ? 'pick-pop border-transparent text-ink' : 'border-line text-ink-2 hover:text-ink'} ${other ? 'opacity-55 hover:opacity-100' : ''}`}
    >
      <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />
      {team}
    </button>
  )
}

function GameRow({ g, d, source, onPick }: { g: LeagueGame; d: Decided | undefined; source: Source; onPick: (team: string) => void }) {
  const p = source === 'student' ? g.p_student : g.p_market
  const fav = p == null ? null : p >= 0.5 ? `${g.home} ${pct(p)}` : `${g.away} ${pct(1 - p)}`
  const won = d ? (d.winner === 'home' ? g.home : g.away) : null
  return (
    <li data-matchup style={matchupVars(g.away, g.home)} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line py-2 text-[13px]">
      <span role="group" aria-label={`Decide ${g.away} at ${g.home}`} className="flex gap-1.5">
        <DecideButton team={g.away} side="away" on={won === g.away} other={won === g.home} onClick={() => onPick(g.away)} />
        <span className="self-center text-ink-3">@</span>
        <DecideButton team={g.home} side="home" on={won === g.home} other={won === g.away} onClick={() => onPick(g.home)} />
      </span>
      <Link to={`/game/${g.game_id}`} title={g.kickoff ? kickoffEt(g.kickoff) : undefined} className="min-w-0 flex-1 text-ink-3 hover:text-ink">
        {fav ? `${source === 'student' ? 'Student' : 'Market'} ${fav}` : 'Game page'}
      </Link>
      {d && d.from !== 'link' && <span className="rounded-full border border-line px-2 py-px text-[11px] text-ink-3">{FROM_LABEL[d.from]}</span>}
    </li>
  )
}

export function WhatIfPanel({ file, scenario, decided, source, nPicks, onChange }: {
  file: LeagueFile
  scenario: Scenario
  decided: Map<string, Decided>
  source: Source
  nPicks: number
  onChange: (s: Scenario) => void
}) {
  const [copied, setCopied] = useState(false)
  const weeks = gamesByWeek(file)
  const copy = () => {
    try {
      void navigator.clipboard?.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // no clipboard: the address bar has the link
    }
  }
  const btn = 'cursor-pointer rounded-md border border-line px-2.5 py-1 text-[13px] text-ink-2 hover:bg-surface-2 hover:text-ink'
  const nDecided = decided.size
  return (
    <section aria-label="What if: decide games" className="flex flex-col gap-3 rounded-lg border border-line bg-surface-1 p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-[14px] font-medium text-ink">Decide games, watch the odds move</span>
        <span className="text-[13px] text-ink-3">{nDecided} of {file.games.length} decided; the rest come from the {source === 'student' ? "Student's" : "market's"} chances</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
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
      </div>
      {weeks.map(([week, games], i) => {
        const list = (
          <ul className="m-0 list-none p-0">
            {games.map((g) => (
              <GameRow key={g.game_id} g={g} d={decided.get(g.game_id)} source={source} onPick={(team) => onChange(toggle(scenario, g, team, decided.get(g.game_id)))} />
            ))}
          </ul>
        )
        const n = games.filter((g) => decided.has(g.game_id)).length
        const title = `Week ${week}${n ? ` · ${n} decided` : ''}`
        return i === 0 ? (
          <div key={week}>
            <div className="text-[12px] font-medium uppercase tracking-wide text-ink-3">{title}</div>
            {list}
          </div>
        ) : (
          <details key={week} className="group">
            <summary className="cursor-pointer text-[12px] font-medium uppercase tracking-wide text-ink-3 hover:text-ink">{title}</summary>
            {list}
          </details>
        )
      })}
    </section>
  )
}
