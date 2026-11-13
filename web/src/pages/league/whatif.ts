/**
 * The playoff what-if (M26.4, ADR 0029): which games are decided, from the URL and your picks.
 *
 * URL: `whatif=1` turns the mode on; `d=<game_id>:<TEAM or ->,…` are the scenario's decisions ("-"
 * leaves a game to the source even when you picked it); `fav=1` gives every game not decided
 * otherwise to the source's favorite; `mypicks=0` ignores your saved picks. Decisions in the link
 * beat your picks, so a shared link always shows exactly its scenario... except picks of the person
 * opening it, which the switch turns off.
 */
import type { LeagueFile, LeagueGame, LeagueOddsTeam } from '../../data/contract'
import type { Picks } from '../../lib/picks'
import type { TeamOdds, Winner } from '../../lib/league/simulate'
import type { Source } from '../../lib/league/input'

export type Choice = string | '-' // a team code, or "left to the source"
export type Scenario = { on: boolean; decisions: Map<string, Choice>; fav: boolean; usePicks: boolean }

export function parseScenario(params: URLSearchParams): Scenario {
  const decisions = new Map<string, Choice>()
  for (const part of (params.get('d') ?? '').split(',')) {
    const i = part.lastIndexOf(':')
    if (i > 0) decisions.set(part.slice(0, i), part.slice(i + 1))
  }
  return { on: params.get('whatif') === '1', decisions, fav: params.get('fav') === '1', usePicks: params.get('mypicks') !== '0' }
}

/** The URL params for a scenario, on top of `prev` (other params kept). Defaults are left out. */
export function writeScenario(prev: URLSearchParams, s: Scenario): URLSearchParams {
  const n = new URLSearchParams(prev)
  const put = (k: string, v: string | null) => (v == null ? n.delete(k) : n.set(k, v))
  put('whatif', s.on ? '1' : null)
  put('d', s.on && s.decisions.size ? [...s.decisions].map(([g, c]) => `${g}:${c}`).join(',') : null)
  put('fav', s.on && s.fav ? '1' : null)
  put('mypicks', s.on && !s.usePicks ? '0' : null)
  return n
}

const pOf = (g: LeagueGame, source: Source) => (source === 'student' ? g.p_student : g.p_market)

export type Decided = { winner: Winner; from: 'link' | 'pick' | 'favorite' }

/** The winner of every decided game, and where the decision came from. Your picks and favorites apply only where the link says nothing. */
export function decide(file: LeagueFile, s: Scenario, picks: Picks, source: Source): Map<string, Decided> {
  const out = new Map<string, Decided>()
  for (const g of file.games) {
    const side = (team: string | undefined): Winner | null => (team === g.home ? 'home' : team === g.away ? 'away' : null)
    const link = s.decisions.get(g.game_id)
    if (link !== undefined) {
      const w = side(link)
      if (w) out.set(g.game_id, { winner: w, from: 'link' })
      continue // "-" or an unknown team: left to the source
    }
    const pick = s.usePicks ? side(picks[g.game_id]?.team) : null
    if (pick) {
      out.set(g.game_id, { winner: pick, from: 'pick' })
      continue
    }
    const p = pOf(g, source)
    if (s.fav && p != null) out.set(g.game_id, { winner: p >= 0.5 ? 'home' : 'away', from: 'favorite' })
  }
  return out
}

export const winners = (d: Map<string, Decided>): Map<string, Winner> => new Map([...d].map(([g, x]) => [g, x.winner]))

/** Your saved picks that land on a game still in the simulation. */
export const picksInPlay = (file: LeagueFile, picks: Picks) =>
  file.games.filter((g) => {
    const t = picks[g.game_id]?.team
    return t === g.home || t === g.away
  }).length

/** The scenario after clicking `team` on game `g` (clicking the decided team again leaves the game to the source). */
export function toggle(s: Scenario, g: LeagueGame, team: string, current: Decided | undefined): Scenario {
  const decisions = new Map(s.decisions)
  const winnerTeam = current ? (current.winner === 'home' ? g.home : g.away) : null
  if (winnerTeam === team) {
    // undo: a link decision is dropped; a pick or favorite is overridden with "-"
    if (current?.from === 'link') decisions.delete(g.game_id)
    else decisions.set(g.game_id, '-')
  } else decisions.set(g.game_id, team)
  return { ...s, decisions }
}

/** Remaining games by week, ascending; kickoff order inside a week. */
export function gamesByWeek(file: LeagueFile): [number, LeagueGame[]][] {
  const weeks = new Map<number, LeagueGame[]>()
  for (const g of file.games) weeks.set(g.week, [...(weeks.get(g.week) ?? []), g])
  return [...weeks.entries()].sort((a, b) => a[0] - b[0]).map(([w, gs]) => [w, gs.sort((a, b) => (a.kickoff ?? '').localeCompare(b.kickoff ?? '') || a.game_id.localeCompare(b.game_id))])
}

/** The engine's odds in the page's shape (wins as p10/p90 and mean). */
export function toOddsTeam(o: TeamOdds): LeagueOddsTeam {
  return { playoffs: o.playoffs, division: o.division, bye: o.bye, seed: o.seed, rounds: o.rounds, wins: { mean: o.winsMean, lo: o.winsLo, hi: o.winsHi } }
}

export type Mover = { team: string; from: number; to: number }

/** Teams whose playoff chance moved at least `min` (probability), biggest first. */
export function movers(now: Record<string, TeamOdds>, next: Record<string, TeamOdds>, teams: string[], min = 0.03): Mover[] {
  return teams
    .filter((t) => now[t] && next[t])
    .map((t) => ({ team: t, from: now[t].playoffs, to: next[t].playoffs }))
    .filter((m) => Math.abs(m.to - m.from) >= min)
    .sort((a, b) => Math.abs(b.to - b.from) - Math.abs(a.to - a.from) || a.team.localeCompare(b.team))
}

/** One team's remaining games, in week order. */
export const teamGames = (file: LeagueFile, team: string): LeagueGame[] => gamesByWeek(file).flatMap(([, gs]) => gs.filter((g) => g.home === team || g.away === team))

/** Decide every game in `games` for (`'win'`) or against (`'lose'`) `team`, or (`'clear'`) drop the link's decisions on them. */
export function setTeamGames(s: Scenario, games: LeagueGame[], team: string, how: 'win' | 'lose' | 'clear'): Scenario {
  const decisions = new Map(s.decisions)
  for (const g of games) {
    if (how === 'clear') decisions.delete(g.game_id)
    else {
      const other = g.home === team ? g.away : g.home
      decisions.set(g.game_id, how === 'win' ? team : other)
    }
  }
  return { ...s, decisions }
}
