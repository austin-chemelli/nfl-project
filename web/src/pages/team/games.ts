/** Pure logic for the team page's Games tab (M18.6): this team's biggest swings and the notes under each game row. */
import type { LeagueFile, LeagueGame, TeamChange, TeamFile, TeamGame } from '../../data/contract'
import { swingSize, swingText, upcoming, MIN_BRANCH_RUNS } from '../league/playoffs'

export const MATTER_SHOWN = 3

export type Matter = { game: LeagueGame; text: string }

/**
 * Upcoming games where this team's own playoff odds move most, biggest swing first, at most three. The line is
 * the League Games tab's, for this team only. A game drops when its branches are too thin, the team has no
 * swing on it, or the team does no better with a win.
 */
export function gamesThatMatter(code: string, league: LeagueFile, now: number = Date.now()): Matter[] {
  return upcoming(league.games, now)
    .flatMap((game) => {
      if (game.n_home_wins < MIN_BRANCH_RUNS || game.n_away_wins < MIN_BRANCH_RUNS) return []
      const s = game.swings.find((x) => x.team === code)
      const text = s && swingText(game, s, league)
      return s && text ? [{ game, text, size: swingSize(s) }] : []
    })
    .sort((a, b) => b.size - a.size || a.game.week - b.game.week || a.game.game_id.localeCompare(b.game.game_id))
    .slice(0, MATTER_SHOWN)
    .map(({ game, text }) => ({ game, text }))
}

const TITLE = { HC: 'head coach', OC: 'offensive coordinator', DC: 'defensive coordinator' } as const

/** One person's changes in one week, as a sentence: a title and play-calling together read as "took over the offense". */
function sentence(name: string, roles: Set<string>): string {
  if (roles.has('HC')) return `${name} became head coach`
  for (const [title, call, side] of [['OC', 'OFF_PC', 'offense'], ['DC', 'DEF_PC', 'defense']] as const) {
    if (roles.has(title) && roles.has(call)) return `${name} took over the ${side}`
    if (roles.has(title)) return `${name} became ${TITLE[title]}`
    if (roles.has(call)) return `${name} took over ${side === 'offense' ? 'offensive' : 'defensive'} play-calling`
  }
  return `${name} joined the staff`
}

/** Staff changes as one line per person per week, keyed by the week they start. */
export function changeLines(changes: TeamChange[]): Map<number, string[]> {
  const byWeek = new Map<number, Map<string, Set<string>>>()
  for (const c of changes) {
    const people = byWeek.get(c.start_week) ?? new Map<string, Set<string>>()
    people.set(c.name, (people.get(c.name) ?? new Set<string>()).add(c.role))
    byWeek.set(c.start_week, people)
  }
  return new Map([...byWeek].map(([week, people]) => [week, [...people].map(([name, roles]) => sentence(name, roles))]))
}

/**
 * Notes under each game, by game id. A change dated to a bye week attaches to the next game played; a change
 * after the last game attaches to none. A starter note goes on the game of that week.
 */
export function gameNotes(games: TeamGame[], file: Pick<TeamFile, 'staff' | 'other_starter_weeks'> | undefined): Map<string, string[]> {
  const notes = new Map<string, string[]>()
  if (!file) return notes
  const ordered = [...games].sort((a, b) => a.week - b.week)
  const add = (id: string, line: string) => notes.set(id, [...(notes.get(id) ?? []), line])
  for (const [week, lines] of [...changeLines(file.staff.changes)].sort((a, b) => a[0] - b[0])) {
    const g = ordered.find((x) => x.week >= week)
    if (g) lines.forEach((l) => add(g.id, l))
  }
  for (const s of [...file.other_starter_weeks].sort((a, b) => a.week - b.week)) {
    const g = ordered.find((x) => x.week === s.week)
    if (g) add(g.id, `${s.qb} started`)
  }
  return notes
}
