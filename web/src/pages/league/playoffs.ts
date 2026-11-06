/** Pure helpers for the League page's playoff tabs (ADR 0019): probability text, the odds table, swings. */
import type { LeagueFile, LeagueGame, LeagueOddsTeam, LeagueSwing, LeagueTeam, LeagueVariant } from '../../data/contract'
import { dash } from '../../lib/format'

export type Conf = 'AFC' | 'NFC'
export type View = 'student' | 'market'

export const parseConf = (raw: string | null): Conf => (raw === 'NFC' ? 'NFC' : 'AFC')
export const parseView = (raw: string | null): View => (raw === 'market' ? 'market' : 'student')

/**
 * A simulated probability as text. Never "0%" or "100%": under 0.1% reads "<0.1%", over 99.9% reads
 * ">99.9%". Near the ends keep a decimal so the rounded integer can't reach 0 or 100.
 */
export function fmtProb(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return dash
  if (p < 0.001) return '<0.1%'
  if (p > 0.999) return '>99.9%'
  const x = 100 * p
  return p < 0.01 || p > 0.99 ? `${x.toFixed(1)}%` : `${Math.round(x)}%`
}

/** The same rule for a bar width: a sliver stays visible and a full bar stays under full. */
export const barWidth = (p: number) => `${Math.min(99.9, Math.max(0.5, 100 * p))}%`

/** Teams of a conference in P(playoffs) order for one variant, with their standing. Teams missing from the variant are left out. */
export function oddsRows(file: LeagueFile, conf: Conf, view: View): { team: LeagueTeam; odds: LeagueOddsTeam }[] {
  const variant = file.odds[view]
  return file.teams
    .filter((t) => t.conf === conf && variant.teams[t.team])
    .map((team) => ({ team, odds: variant.teams[team.team] }))
    .sort((a, b) => b.odds.playoffs - a.odds.playoffs || a.team.team.localeCompare(b.team.team))
}

export const recordOf = (t: Pick<LeagueTeam, 'w' | 'l' | 't'>) => `${t.w}–${t.l}${t.t ? `–${t.t}` : ''}`

/** "p10 to p90" wins as "9–13", one number when they agree. */
export const winsRange = (w: { lo: number; hi: number }) => (w.lo === w.hi ? `${w.lo}` : `${w.lo}–${w.hi}`)

const SOURCE_PHRASE: Record<string, (n: number) => string> = {
  locked: (n) => `${n} from its locked picks`,
  scored: (n) => `${n} scored fresh at the last build`,
  line: (n) => `${n} from the betting line`,
  ratings: (n) => `${n} filled in from ratings fitted to market prices`,
}

/** "14 from its locked picks, 137 scored fresh at the last build"; an unknown key prints as "N key". */
export function sourcesText(v: Pick<LeagueVariant, 'sources'>): string {
  return Object.entries(v.sources)
    .map(([k, n]) => (SOURCE_PHRASE[k] ?? ((m: number) => `${m} ${k}`))(n))
    .join(', ')
}

/** Lines only reach about a week ahead, so most of this view is an estimate. Null once every game has a line. */
export function marketNote(v: Pick<LeagueVariant, 'sources'>): string | null {
  const line = v.sources.line ?? 0
  const total = Object.values(v.sources).reduce((a, b) => a + b, 0)
  if (line === total) return null
  return `Only ${line} of the ${total} games left have a betting line yet. The rest are estimated from this season's lines, so read this as a rough market view.`
}

/** Games from the earliest week that still has one: "this week" on the Games tab and the game-of-the-week tile. */
export function nextWeek(games: LeagueGame[]): number | null {
  return games.length ? Math.min(...games.map((g) => g.week)) : null
}

/** Both branches need this many Student runs before a swing is believed (ADR 0019). */
export const MIN_BRANCH_RUNS = 1000

export const swingSize = (s: LeagueSwing) => Math.abs(s.if_home_win - s.if_away_win)

/**
 * One swing as a sentence part: the team's chance now (the Student's), then its chance on the branch that
 * helps it. For a team in the game that branch is its own win: "CHI 55% → 80% with a win". For another team
 * it is whichever side's win helps: "CHI 55% → 80% if MIN wins". Null when the Student has no odds for the team.
 */
export function swingText(g: Pick<LeagueGame, 'home' | 'away'>, s: LeagueSwing, file: Pick<LeagueFile, 'odds'>): string | null {
  const now = file.odds.student.teams[s.team]?.playoffs
  if (now == null) return null
  const homeHelps = s.if_home_win >= s.if_away_win
  const to = homeHelps ? s.if_home_win : s.if_away_win
  const cond = s.team === g.home ? (homeHelps ? 'with a win' : null) : s.team === g.away ? (homeHelps ? null : 'with a win') : `if ${homeHelps ? g.home : g.away} wins`
  // A team that does better when it loses is not a story this line tells.
  return cond ? `${s.team} ${fmtProb(now)} → ${fmtProb(to)} ${cond}` : null
}

/** A game's swings, biggest first, as text; reporting only swings the file kept and branches with enough runs. */
export function swingLines(g: LeagueGame, file: LeagueFile): string[] {
  if (g.n_home_wins < MIN_BRANCH_RUNS || g.n_away_wins < MIN_BRANCH_RUNS) return []
  return [...g.swings]
    .sort((a, b) => swingSize(b) - swingSize(a) || a.team.localeCompare(b.team))
    .flatMap((s) => swingText(g, s, file) ?? [])
}

/** Next week's games by leverage, then the rest by week and leverage. */
/** The tab is the games that matter, not the schedule: 151 rows ran past 20,000 px on a phone. */
export const LATER_GAMES = 10

export function gamesByLeverage(games: LeagueGame[]): { next: LeagueGame[]; rest: LeagueGame[]; week: number | null } {
  const week = nextWeek(games)
  const lev = (a: LeagueGame, b: LeagueGame) => b.leverage_total - a.leverage_total || a.game_id.localeCompare(b.game_id)
  return {
    week,
    next: games.filter((g) => g.week === week).sort(lev),
    rest: games.filter((g) => g.week !== week).sort(lev).slice(0, LATER_GAMES),
  }
}

/** Divisions of a conference in file order of name (East, North, South, West), each team by division rank. */
export function divisionTables(teams: LeagueTeam[], conf: Conf): { division: string; teams: LeagueTeam[] }[] {
  const names = [...new Set(teams.filter((t) => t.conf === conf).map((t) => t.div))].sort()
  return names.map((division) => ({ division, teams: teams.filter((t) => t.div === division).sort((a, b) => a.div_rank - b.div_rank) }))
}
