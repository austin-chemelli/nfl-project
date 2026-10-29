import { describe, expect, it } from 'vitest'
import type { GameRow } from '../../data/contract'
import { correct, disagreements, divergenceText, homeWon, neighbours, pickOf, sideText } from './helpers'

const pick = (p: number, div: number | null = null) => ({ p_home: p, spread_home: null, status: 'preview' as const, lock_ts: null, divergence: div })
const game = (over: Partial<GameRow> = {}): GameRow => ({
  game_id: 'g', season: 2026, week: 8, kickoff_utc: '2026-10-30T00:15:00Z', away: 'CAR', home: 'GB', stadium: null, roof: null,
  neutral_site: false, away_qb: null, home_qb: null, result: null, market: null,
  models: { traditionalist: pick(0.7), analyst: pick(0.4), sharp: pick(0.55), student: pick(0.5), ensemble: pick(0.54) },
  ...over,
})

describe('slate helpers', () => {
  it('picks the favored side', () => {
    expect(pickOf(game(), 'traditionalist')).toMatchObject({ team: 'GB', home: true })
    expect(pickOf(game(), 'analyst')?.team).toBe('CAR')
    expect(pickOf(game(), 'analyst')?.p).toBeCloseTo(0.6)
    expect(pickOf(game(), 'nope')).toBeNull()
  })
  it('scores correctness only for finished games', () => {
    expect(correct(game(), 'analyst')).toBeNull()
    const final = game({ result: { home_score: 20, away_score: 10, margin: 10 } })
    expect(homeWon(final)).toBe(true)
    expect(correct(final, 'traditionalist')).toBe(true)
    expect(correct(final, 'analyst')).toBe(false)
    expect(homeWon(game({ result: { home_score: 10, away_score: 10, margin: 0 } }))).toBeNull()
  })
  it('ranks disagreement by spread', () => {
    const calm = game({ game_id: 'calm', models: { traditionalist: pick(0.6), analyst: pick(0.61), sharp: pick(0.6), student: pick(0.6) } })
    const top = disagreements([calm, game({ game_id: 'wild' })])
    expect(top.map((d) => d.game.game_id)).toEqual(['wild', 'calm'])
    expect(top[0]).toMatchObject({ hi: 'traditionalist', lo: 'analyst' })
    expect(top[0].spread).toBeCloseTo(0.3)
  })
  it('words', () => {
    expect(sideText(game(), 0.3)).toBe('CAR 70%')
    expect(divergenceText(0.06, game())).toBe('6 pts more on GB than the market')
    expect(divergenceText(-0.08, game())).toBe('8 pts more on CAR than the market')
  })
  it('finds neighbours', () => {
    expect(neighbours([1, 2, 3], 1)).toEqual({ prev: null, next: 2 })
    expect(neighbours([1, 2, 3], 3)).toEqual({ prev: 2, next: null })
    expect(neighbours([1, 2, 3], 9)).toEqual({ prev: null, next: null })
  })
})
