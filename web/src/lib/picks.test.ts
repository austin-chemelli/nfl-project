import { beforeEach, describe, expect, it } from 'vitest'
import type { GameRow } from '../data/contract'
import { clearOpenPicks, getPicks, pickedWeeks, pickOpen, PICKS_KEY, resetPicksCache, scorePicks, setPick, weekOf, type Picks } from './picks'

const KICK = '2026-11-15T18:00:00Z'
const before = new Date('2026-11-14T12:00:00Z')
const after = new Date('2026-11-15T18:30:00Z')

function game(id: string, over: Partial<GameRow> = {}): GameRow {
  const [, , away, home] = id.split('_')
  return {
    game_id: id, season: 2026, week: Number(id.split('_')[1]), kickoff_utc: KICK, away, home,
    result: null, market: { p_home: 0.6 }, models: { student: { p_home: 0.55 } }, ...over,
  } as unknown as GameRow
}

beforeEach(() => {
  localStorage.clear()
  resetPicksCache()
})

describe('picks store', () => {
  it('sets, replaces and clears a pick before kickoff, and saves it', () => {
    const g = game('2026_11_BUF_KC')
    expect(setPick(g, 'BUF', before)).toBe(true)
    expect(getPicks()['2026_11_BUF_KC']).toEqual({ team: 'BUF', at: before.toISOString() })
    setPick(g, 'KC', before)
    expect(JSON.parse(localStorage.getItem(PICKS_KEY)!)['2026_11_BUF_KC'].team).toBe('KC')
    setPick(g, null, before)
    expect(getPicks()).toEqual({})
  })

  it('refuses a pick after kickoff, on a finished game, or for a team not in the game', () => {
    expect(setPick(game('2026_11_BUF_KC'), 'BUF', after)).toBe(false)
    expect(setPick(game('2026_11_BUF_KC', { result: { home_score: 1, away_score: 0, margin: 1 } }), 'BUF', before)).toBe(false)
    expect(setPick(game('2026_11_BUF_KC'), 'NYJ', before)).toBe(false)
    expect(getPicks()).toEqual({})
  })

  it('starts empty on a corrupt value and drops malformed entries', () => {
    localStorage.setItem(PICKS_KEY, '{nope')
    expect(getPicks()).toEqual({})
    resetPicksCache()
    localStorage.setItem(PICKS_KEY, JSON.stringify({ a: { team: 'KC', at: 'x' }, b: { team: 3 }, c: null }))
    expect(Object.keys(getPicks())).toEqual(['a'])
  })

  it('clears only the open picks', () => {
    const open = game('2026_11_BUF_KC', { kickoff_utc: '2099-01-01T00:00:00Z' })
    const done = game('2026_11_NYJ_MIA', { kickoff_utc: '2000-01-01T00:00:00Z' })
    localStorage.setItem(PICKS_KEY, JSON.stringify({ [open.game_id]: { team: 'KC', at: 'x' }, [done.game_id]: { team: 'MIA', at: 'x' } }))
    clearOpenPicks([open, done])
    expect(Object.keys(getPicks())).toEqual([done.game_id])
  })

  it('reads the week from the id and lists picked weeks of one season', () => {
    expect(weekOf('2026_09_BUF_KC')).toEqual({ season: 2026, week: 9 })
    expect(weekOf('junk')).toBeNull()
    const p: Picks = { '2026_10_A_B': { team: 'A', at: '' }, '2026_08_C_D': { team: 'C', at: '' }, '2025_08_E_F': { team: 'E', at: '' } }
    expect(pickedWeeks(p, 2026)).toEqual([8, 10])
  })

  it('a game is open until kickoff', () => {
    expect(pickOpen(game('2026_11_BUF_KC'), before.getTime())).toBe(true)
    expect(pickOpen(game('2026_11_BUF_KC'), after.getTime())).toBe(false)
  })
})

describe('scorePicks', () => {
  const won = (margin: number) => ({ result: { home_score: margin > 0 ? margin : 0, away_score: margin < 0 ? -margin : 0, margin } })
  const at = before.toISOString()

  it('scores you, the model and the market on the same finished games', () => {
    const games = [
      game('2026_11_BUF_KC', won(3)), // home won: you KC ✓, student KC ✓, market KC ✓
      game('2026_11_NYJ_MIA', won(-7)), // away won: you NYJ ✓, student MIA ✗, market MIA ✗
      game('2026_11_DAL_PHI', won(10)), // not picked: not counted
      game('2026_11_SF_SEA'), // picked, not played: pending
    ]
    const picks: Picks = { '2026_11_BUF_KC': { team: 'KC', at }, '2026_11_NYJ_MIA': { team: 'NYJ', at }, '2026_11_SF_SEA': { team: 'SF', at } }
    expect(scorePicks(picks, games, 'student')).toEqual({ games: 2, you: { w: 2, l: 0 }, model: { w: 1, l: 1 }, market: { w: 1, l: 1 }, pending: 1 })
  })

  it('skips ties, picks stamped at or after kickoff, and a side missing from a source', () => {
    const games = [
      game('2026_11_BUF_KC', won(0)),
      game('2026_11_NYJ_MIA', won(3)),
      game('2026_11_DAL_PHI', { ...won(3), market: { p_home: null }, models: {} } as Partial<GameRow>),
    ]
    const picks: Picks = {
      '2026_11_BUF_KC': { team: 'KC', at },
      '2026_11_NYJ_MIA': { team: 'MIA', at: KICK },
      '2026_11_DAL_PHI': { team: 'DAL', at },
    }
    expect(scorePicks(picks, games, 'student')).toEqual({ games: 1, you: { w: 0, l: 1 }, model: { w: 0, l: 0 }, market: { w: 0, l: 0 }, pending: 0 })
  })
})
