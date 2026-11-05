import { describe, expect, it } from 'vitest'
import type { CardData, GameRow, Meta } from '../../data/contract'
import { approachSpread, cardSentence, contrastLine, correct, disagreements, divergenceText, gameStatus, homeWon, neighbours, parseSort, pickOf, sideText, sortGames, whyLine, winnerMarketP } from './helpers'

const pick = (p: number, div: number | null = null) => ({ p_home: p, spread_home: null, status: 'preview' as const, lock_ts: null, divergence: div })
const game = (over: Partial<GameRow> = {}): GameRow => ({
  game_id: 'g', season: 2026, week: 8, kickoff_utc: '2026-10-30T00:15:00Z', away: 'CAR', home: 'GB', stadium: null, roof: null,
  neutral_site: false, away_qb: null, home_qb: null, result: null, market: null, card: null,
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

describe('whyLine', () => {
  const meta = { groups: { groups: [{ id: 'form', name: 'Form', context_only: false }, { id: 'coaching', name: 'Coaching', context_only: true }] } } as unknown as Meta
  const card = (over: Partial<CardData> = {}): CardData => ({ edges: {}, injuries: [], usual_qb: { home: null, away: null }, weather_concern: null, contrast: null, ...over })
  const withCard = (c: Partial<CardData> | null, over: Partial<GameRow> = {}) => game({ roof: 'outdoors', card: c == null ? null : card(c), ...over })
  const edge = (pct: number, id = 'form') => ({ [id]: { favors: 'JAX', strength_pct: pct } })
  const out = { team: 'BAL', player: 'A Name', pos: 'WR', status: 'Out' }

  it('names a neutral site, and never calls one a venue edge', () => {
    const card = { edges: { venue_weather: { favors: 'CAR', strength_pct: 98 } }, injuries: [], usual_qb: { home: null, away: null }, weather_concern: null, contrast: null }
    const g = game({ neutral_site: true, stadium: 'Bernabeu', card })
    expect(whyLine(g, meta)).toBe('Neutral site: Bernabeu')
    expect(whyLine(game({ card }), meta)).toBeNull()
  })

  it('is null with no card, no pieces and no edges, or a finished game', () => {
    expect(whyLine(withCard(null), meta)).toBeNull()
    expect(whyLine(withCard({}), meta)).toBeNull()
    expect(whyLine(withCard({ injuries: [out] }, { result: { home_score: 1, away_score: 0, margin: 1 } }), meta)).toBeNull()
  })
  it('names a new starter, an absence, an edge and weather', () => {
    expect(whyLine(withCard({ usual_qb: { home: 'Jordan Love', away: null } }, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob starts for GB (usually Jordan Love)')
    expect(whyLine(withCard({ injuries: [out] }), meta)).toBe('BAL without A Name (WR)')
    expect(whyLine(withCard({ edges: edge(92) }), meta)).toBe('JAX Form edge, bigger than 92% of matchups')
    expect(whyLine(withCard({ weather_concern: 0.5 }), meta)).toBe('Weather could be a factor')
  })
  it('says doubtful for a doubtful player', () => {
    expect(whyLine(withCard({ injuries: [{ ...out, status: 'Doubtful' }] }), meta)).toBe("BAL's A Name doubtful")
  })
  it('keeps two pieces, in order', () => {
    const c = { usual_qb: { home: 'Jordan Love', away: null }, injuries: [out], edges: edge(92), weather_concern: 0.8 }
    expect(whyLine(withCard(c, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob starts for GB (usually Jordan Love) · BAL without A Name (WR)')
    expect(whyLine(withCard({ ...c, injuries: [] }), meta)).toBe('JAX Form edge, bigger than 92% of matchups · Weather could be a factor')
  })
  it('names a player once when the QB piece and the absence agree', () => {
    const qb = { team: 'GB', player: 'Jordan Love', pos: 'QB', status: 'Out' }
    expect(whyLine(withCard({ usual_qb: { home: 'Jordan Love', away: null }, injuries: [qb] }, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob starts for GB (usually Jordan Love)')
    // the next absence still shows
    expect(whyLine(withCard({ usual_qb: { home: 'Jordan Love', away: null }, injuries: [qb, out] }, { home_qb: 'Backup Bob' }), meta)).toContain('BAL without A Name (WR)')
  })
  it('lists both teams with a new starter', () => {
    const g = withCard({ usual_qb: { home: 'Jordan Love', away: 'Bryce Young' } }, { home_qb: 'Backup Bob', away_qb: 'Other Guy' })
    expect(whyLine(g, meta)).toBe('Other Guy starts for CAR (usually Bryce Young) · Backup Bob starts for GB (usually Jordan Love)')
  })
  it('ignores a starter who matches the usual one', () => {
    expect(whyLine(withCard({ usual_qb: { home: 'Jordan Love', away: null } }, { home_qb: 'Jordan Love' }), meta)).toBeNull()
  })
  it('uses edges at 75 and above; below that it is no standout edge', () => {
    expect(whyLine(withCard({ edges: edge(75) }), meta)).toContain('edge, bigger than 75%')
    expect(whyLine(withCard({ edges: edge(74.9) }), meta)).toBe('No standout edge')
  })
  it('skips context-only groups as edges', () => {
    expect(whyLine(withCard({ edges: edge(99, 'coaching') }), meta)).toBeNull()
  })
  it('mentions weather only outdoors (or open) and at 0.5 or more', () => {
    expect(whyLine(withCard({ weather_concern: 0.49 }), meta)).toBeNull()
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: 'dome' }), meta)).toBeNull()
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: 'closed' }), meta)).toBeNull()
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: 'open' }), meta)).toBe('Weather could be a factor')
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: null }), meta)).toBeNull()
  })
})

describe('contrastLine', () => {
  const contrast = { offense: 'JAX', defense: 'BAL', off_label: 'pass-heavy', def_label: 'blitz-heavy', off_rank: 3, def_rank: 1 }
  const c = (x: typeof contrast | null) => ({ edges: {}, injuries: [], usual_qb: { home: null, away: null }, weather_concern: null, contrast: x })
  it('reads most for rank 1 and the ordinal otherwise', () => {
    expect(contrastLine(game({ card: c(contrast) }))).toBe("JAX's 3rd-most pass-heavy offense faces BAL's most blitz-heavy defense")
    expect(contrastLine(game({ card: c({ ...contrast, off_rank: 1, def_rank: 2 }) }))).toBe("JAX's most pass-heavy offense faces BAL's 2nd-most blitz-heavy defense")
  })
  it('is null on a finished game, without a contrast or without a card', () => {
    expect(contrastLine(game({ card: c(contrast), result: { home_score: 1, away_score: 0, margin: 1 } }))).toBeNull()
    expect(contrastLine(game({ card: c(null) }))).toBeNull()
    expect(contrastLine(game())).toBeNull()
  })
})
