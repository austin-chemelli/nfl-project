import { describe, expect, it } from 'vitest'
import type { LeagueFile, LeagueGame, TeamChange, TeamGame } from '../../data/contract'
import { changeLines, gameNotes, gamesThatMatter } from './games'

const league = { odds: { market: { teams: { CAR: { playoffs: 0.2 } } } } } as unknown as LeagueFile
const game = (id: string, week: number, hi: number, lo: number, over: Partial<LeagueGame> = {}): LeagueGame =>
  ({
    game_id: id, week, kickoff: `2026-11-${10 + week}T18:00:00Z`, home: 'CAR', away: 'TB', p_student: 0.5, p_market: null,
    market_source: null, leverage_total: 0, n_home_wins: 5000, n_away_wins: 5000,
    swings: [{ team: 'CAR', if_home_win: hi, if_away_win: lo }], ...over,
  }) as LeagueGame
const NOW = Date.parse('2026-11-01T00:00:00Z')
const withGames = (games: LeagueGame[]) => ({ ...league, games }) as LeagueFile

describe('gamesThatMatter', () => {
  it('orders by swing, biggest first, and caps at three', () => {
    const f = withGames([game('a', 1, 0.3, 0.25), game('b', 2, 0.5, 0.2), game('c', 3, 0.4, 0.3), game('d', 4, 0.35, 0.1), game('e', 5, 0.9, 0.85)])
    expect(gamesThatMatter('CAR', f, NOW).map((m) => m.game.game_id)).toEqual(['b', 'd', 'c'])
  })

  it('prints the League Games line', () => {
    const [m] = gamesThatMatter('CAR', withGames([game('a', 1, 0.5, 0.2)]), NOW)
    expect(m.text).toBe('CAR 20% → 50% with a win')
  })

  it('skips finished games, thin branches, other teams and swings that favor a loss', () => {
    const f = withGames([
      game('past', 1, 0.9, 0.1, { kickoff: '2026-10-01T18:00:00Z' }),
      game('thin', 2, 0.9, 0.1, { n_away_wins: 10 }),
      game('other', 3, 0.9, 0.1, { swings: [{ team: 'TB', if_home_win: 0.9, if_away_win: 0.1 }] }),
      game('loss', 4, 0.1, 0.6),
    ])
    expect(gamesThatMatter('CAR', f, NOW)).toEqual([])
  })
})

const change = (role: string, name: string, start_week: number): TeamChange =>
  ({ role, name, start_week, end_week: null, evidence: 'official', confirmed: true, source_url: null, replaced: null }) as TeamChange
const tg = (week: number): TeamGame => ({ id: `g${week}`, week, opp: 'X', home: true, pf: null, pa: null })

describe('changeLines', () => {
  it('merges a title and play-calling change by one person into one line', () => {
    const m = changeLines([change('DC', 'Todd Wash', 9), change('DEF_PC', 'Todd Wash', 9)])
    expect(m.get(9)).toEqual(['Todd Wash took over the defense'])
  })

  it('keeps single changes and different people apart', () => {
    const m = changeLines([change('OC', 'A B', 5), change('DEF_PC', 'C D', 5), change('HC', 'E F', 6)])
    expect(m.get(5)).toEqual(['A B became offensive coordinator', 'C D took over defensive play-calling'])
    expect(m.get(6)).toEqual(['E F became head coach'])
  })
})

describe('gameNotes', () => {
  const staff = (changes: TeamChange[]) => ({ staff: { current: [], changes }, other_starter_weeks: [] as { week: number; qb: string }[] })

  it('puts a change on a bye week on the next game played', () => {
    const notes = gameNotes([tg(4), tg(6), tg(7)], staff([change('DC', 'Todd Wash', 5)]))
    expect(notes.get('g6')).toEqual(['Todd Wash became defensive coordinator'])
    expect(notes.has('g4')).toBe(false)
  })

  it('drops a change after the last game and adds starters by week', () => {
    const f = { ...staff([change('HC', 'Z', 20)]), other_starter_weeks: [{ week: 6, qb: 'Drew Lock' }] }
    const notes = gameNotes([tg(4), tg(6)], f)
    expect(notes.get('g6')).toEqual(['Drew Lock started'])
    expect(notes.size).toBe(1)
  })

  it('is empty without a file', () => {
    expect(gameNotes([tg(1)], undefined).size).toBe(0)
  })
})
