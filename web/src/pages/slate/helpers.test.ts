import { describe, expect, it } from 'vitest'
import type { GameRow } from '../../data/contract'
import { approachSpread, cardSentence, correct, disagreements, divergenceText, gameStatus, homeWon, neighbours, parseSort, pickOf, sideText, sortGames, winnerMarketP } from './helpers'

const pick = (p: number, div: number | null = null) => ({ p_home: p, spread_home: null, status: 'preview' as const, lock_ts: null, divergence: div })
const game = (over: Partial<GameRow> = {}): GameRow => ({
  game_id: 'g', season: 2026, week: 8, kickoff_utc: '2026-10-30T00:15:00Z', away: 'CAR', home: 'GB', stadium: null, roof: null,
  neutral_site: false, away_qb: null, home_qb: null, result: null, market: null,
  models: { traditionalist: pick(0.7), analyst: pick(0.4), sharp: pick(0.55), student: pick(0.5) },
  ...over,
})

describe('slate helpers', () => {
  it('says when no approach has scored a game', () => {
    expect(gameStatus(game({ models: {} }))).toEqual({ status: 'none', lockTs: null })
    expect(gameStatus(game()).status).toBe('preview')
  })
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

const mk = (p: number) => ({ p_home: p, spread_home: null, total: null, as_of: null, source: null }) as unknown as GameRow['market']
const finalOf = (margin: number) => ({ home_score: margin > 0 ? 24 : 17, away_score: margin > 0 ? 17 : 24, margin })
const models = (a: number, s: number, t = a, st = a) => ({ traditionalist: pick(t), analyst: pick(a), sharp: pick(s), student: pick(st) })

describe('cardSentence', () => {
  it('pregame: names the approach furthest from the market', () => {
    expect(cardSentence(game({ market: mk(0.7), models: models(0.72, 0.58) }))).toBe('Sharp is 12 pts from the market on CHI'.replace('CHI', 'CAR'))
    expect(cardSentence(game({ market: mk(0.5), models: models(0.52, 0.64) }))).toBe('Sharp is 14 pts from the market on GB')
  })
  it('pregame: all agree with the market', () => {
    expect(cardSentence(game({ market: mk(0.65), models: models(0.66, 0.68) }))).toBe('All four agree with the market')
  })
  it('pregame: splits', () => {
    expect(cardSentence(game({ market: mk(0.5), models: models(0.4, 0.6, 0.6, 0.4) }))).toBe('Approaches split 2–2')
    expect(cardSentence(game({ market: mk(0.6), models: models(0.6, 0.4, 0.6, 0.6) }))).toBe('Split 3–1 GB; Sharp takes CAR')
  })
  it('pregame: unanimous against the market, and with no line', () => {
    expect(cardSentence(game({ market: mk(0.48), models: models(0.52, 0.53) }))).toBe('All four pick GB; the market leans CAR')
    expect(cardSentence(game({ market: null, models: models(0.6, 0.7) }))).toBe('All four pick GB')
    expect(cardSentence(game({ models: {} }))).toBe('Not scored yet')
  })
  it('finished: upset only outside the toss-up band', () => {
    expect(cardSentence(game({ market: mk(0.61), result: finalOf(-3), models: models(0.6, 0.6) }))).toBe('Upset: CAR won as a 39% underdog')
    expect(cardSentence(game({ market: mk(0.52), result: finalOf(-3), models: models(0.6, 0.6) }))).toBe('All four picked GB; CAR won')
  })
  it('finished: who called it', () => {
    const base = { market: mk(0.6), result: finalOf(7) }
    expect(cardSentence(game({ ...base, models: models(0.6, 0.6) }))).toBe('All four picked GB')
    expect(cardSentence(game({ ...base, models: models(0.4, 0.4, 0.6, 0.6) }))).toBe('Traditionalist and Student called it')
    expect(cardSentence(game({ ...base, models: models(0.6, 0.4, 0.6, 0.6) }))).toBe('Sharp missed it')
    expect(cardSentence(game({ ...base, result: finalOf(0), models: models(0.6, 0.6) }))).toBe('Ended in a tie')
  })
})

describe('sortGames', () => {
  const a = game({ game_id: 'a', kickoff_utc: '2026-10-30T17:00:00Z', market: mk(0.8), result: finalOf(7), models: models(0.5, 0.5) }) // favorite won
  const b = game({ game_id: 'b', kickoff_utc: '2026-10-30T18:00:00Z', market: mk(0.7), result: finalOf(-3), models: models(0.2, 0.9) }) // upset (30%), wide spread
  const c = game({ game_id: 'c', kickoff_utc: '2026-10-29T18:00:00Z', market: mk(0.6), models: models(0.6, 0.65) }) // unplayed, calm
  const d = game({ game_id: 'd', kickoff_utc: '2026-10-31T18:00:00Z', models: {} }) // nothing scored
  const ids = (xs: GameRow[]) => xs.map((g) => g.game_id)
  it('kickoff', () => expect(ids(sortGames([a, b, c, d], 'kickoff'))).toEqual(['c', 'a', 'b', 'd']))
  it('disagreement: widest first, unscored last', () => expect(ids(sortGames([a, b, c, d], 'disagreement'))).toEqual(['b', 'c', 'a', 'd']))
  it('upset: lowest winner chance first, then the unplayed by kickoff', () => expect(ids(sortGames([a, b, c, d], 'upset'))).toEqual(['b', 'a', 'c', 'd']))
  it('upset: unplayed games keep kickoff order whatever the input order', () => {
    const e = game({ game_id: 'e', kickoff_utc: '2026-10-29T12:00:00Z', market: mk(0.5), models: models(0.5, 0.5) })
    expect(ids(sortGames([d, c, e, b, a], 'upset'))).toEqual(['b', 'a', 'e', 'c', 'd'])
  })
  it('spread, winner market and sort parsing', () => {
    expect(approachSpread(b)).toBeCloseTo(0.7)
    expect(approachSpread(d)).toBeNull()
    expect(winnerMarketP(b)).toBeCloseTo(0.3)
    expect(winnerMarketP(c)).toBeNull()
    expect(parseSort('upset')).toBe('upset')
    expect(parseSort('nope')).toBe('kickoff')
  })
})

describe('gameStatus', () => {
  const m = (status: string) => ({ ...pick(0.5), status: status as 'locked', lock_ts: status })
  const row = (models: GameRow['models']) => game({ models })
  it('reads the Student, whatever else the row carries and in whatever order', () => {
    expect(gameStatus(row({ market_baseline: m('preview'), student: m('locked') }))).toEqual({ status: 'locked', lockTs: 'locked' })
  })
  it('falls back to an approach, then a reference, never to the key order', () => {
    expect(gameStatus(row({ global: m('pregame'), elo_v0: m('backfill'), sharp: m('locked') })).status).toBe('locked')
    expect(gameStatus(row({ global: m('pregame'), elo_v0: m('backfill') })).status).toBe('backfill')
    expect(gameStatus(row({})).status).toBe('none')
  })
})
