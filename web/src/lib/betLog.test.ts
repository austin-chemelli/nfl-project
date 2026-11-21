import { beforeEach, describe, expect, it } from 'vitest'
import type { ClosingGame } from '../data/contract'
import {
  addBet, americanFromCents, betClv, betProfit, BETS_KEY, decimalOdds, deleteBet, getBets, gradeBet, importBets, mergeImport,
  parseEntry, resetBetsCache, summarize, toCsv, validPrice, type BetEntry,
} from './betLog'

const game = (home_score: number | null, away_score: number | null, close: Partial<NonNullable<ClosingGame['close']>> | null = null): ClosingGame => ({
  game_id: 'g1', week: 1, kickoff_utc: '2026-11-15T18:00:00Z', away: 'AAA', home: 'HHH', home_score, away_score,
  close: close == null ? null : { as_of: '2026-11-15T17:00:00Z', p_home: null, home_ml: null, away_ml: null, spread_home: null, total: null, ...close },
})
const bet = (o: Partial<BetEntry> = {}): BetEntry => ({
  id: 'b1', game_id: 'g1', market: 'ml', side: 'home', line: null, price: -200, stake: 10, fee: 0, venue: 'Kalshi', placed_at: '2026-11-14T12:00:00Z', ...o,
})

describe('grading', () => {
  it('moneyline: win, loss, push, open', () => {
    expect(gradeBet(bet(), game(24, 20))).toBe('win')
    expect(gradeBet(bet(), game(20, 24))).toBe('loss')
    expect(gradeBet(bet(), game(20, 20))).toBe('push')
    expect(gradeBet(bet({ side: 'away' }), game(20, 24))).toBe('win')
    expect(gradeBet(bet(), game(null, null))).toBe('open')
    expect(gradeBet(bet(), undefined)).toBe('open')
  })

  it('spread: half points never push, whole points can', () => {
    const fav = bet({ market: 'spread', side: 'home', line: -3.5 })
    expect(gradeBet(fav, game(27, 20))).toBe('win')
    expect(gradeBet(fav, game(23, 20))).toBe('loss')
    const whole = bet({ market: 'spread', side: 'home', line: -3 })
    expect(gradeBet(whole, game(23, 20))).toBe('push')
    expect(gradeBet(whole, game(24, 20))).toBe('win')
    const dog = bet({ market: 'spread', side: 'away', line: 3.5 })
    expect(gradeBet(dog, game(23, 20))).toBe('win')
    expect(gradeBet(dog, game(27, 20))).toBe('loss')
    expect(gradeBet(bet({ market: 'spread', side: 'away', line: 7 }), game(27, 20))).toBe('push')
  })

  it('total: over and under, with a push on the number', () => {
    const over = bet({ market: 'total', side: 'over', line: 44.5 })
    expect(gradeBet(over, game(30, 20))).toBe('win')
    expect(gradeBet(over, game(20, 20))).toBe('loss')
    const under = bet({ market: 'total', side: 'under', line: 44.5 })
    expect(gradeBet(under, game(20, 20))).toBe('win')
    expect(gradeBet(under, game(30, 20))).toBe('loss')
    expect(gradeBet(bet({ market: 'total', side: 'under', line: 40 }), game(20, 20))).toBe('push')
  })
})

describe('profit', () => {
  it('pays at the price, less the fee', () => {
    expect(betProfit(bet({ price: -200, stake: 10 }), 'win')).toBeCloseTo(5)
    expect(betProfit(bet({ price: 150, stake: 10 }), 'win')).toBeCloseTo(15)
    expect(betProfit(bet({ price: -200, stake: 10, fee: 0.5 }), 'win')).toBeCloseTo(4.5)
    expect(betProfit(bet({ stake: 10, fee: 0.5 }), 'loss')).toBeCloseTo(-10.5)
    expect(betProfit(bet({ stake: 10, fee: 0.5 }), 'push')).toBeCloseTo(-0.5)
    expect(betProfit(bet(), 'open')).toBeNull()
  })
})

describe('closing-line value', () => {
  it('moneyline: the closing fair chance minus the chance the price implies, in points', () => {
    // paid -200 (66.7%); the close fair chance of home was 70%
    expect(betClv(bet({ price: -200 }), game(1, 0, { p_home: 0.7 }))).toBeCloseTo(100 * (0.7 - 2 / 3))
    // away side uses 1 - p_home
    expect(betClv(bet({ side: 'away', price: 150 }), game(1, 0, { p_home: 0.7 }))).toBeCloseTo(100 * (0.3 - 0.4))
    expect(betClv(bet(), game(1, 0, { p_home: null }))).toBeNull()
    expect(betClv(bet(), game(1, 0, null))).toBeNull()
  })

  it('spread: the line you took against the closing point of your side', () => {
    // spread_home +5 means home favored by 5: the home closing point is -5
    expect(betClv(bet({ market: 'spread', side: 'home', line: -3.5 }), game(1, 0, { spread_home: 5 }))).toBeCloseTo(1.5)
    expect(betClv(bet({ market: 'spread', side: 'away', line: 6.5 }), game(1, 0, { spread_home: 5 }))).toBeCloseTo(1.5)
    expect(betClv(bet({ market: 'spread', side: 'home', line: -6 }), game(1, 0, { spread_home: 5 }))).toBeCloseTo(-1)
  })

  it('total: under likes a higher number, over a lower one', () => {
    expect(betClv(bet({ market: 'total', side: 'under', line: 46 }), game(1, 0, { total: 44.5 }))).toBeCloseTo(1.5)
    expect(betClv(bet({ market: 'total', side: 'over', line: 43 }), game(1, 0, { total: 44.5 }))).toBeCloseTo(1.5)
    expect(betClv(bet({ market: 'total', side: 'over', line: 46 }), game(1, 0, { total: 44.5 }))).toBeCloseTo(-1.5)
  })
})

describe('prices', () => {
  it('converts a cents price to American through decimal = 100 / cents', () => {
    expect(americanFromCents(50)).toBe(100)
    expect(americanFromCents(20)).toBe(400)
    expect(americanFromCents(80)).toBe(-400)
    expect(americanFromCents(65)).toBe(-186)
    expect(americanFromCents(0)).toBeNull()
    expect(americanFromCents(100)).toBeNull()
    expect(decimalOdds(-200)).toBeCloseTo(1.5)
  })

  it('rejects a price inside ±100', () => {
    expect(validPrice(-110)).toBe(true)
    expect(validPrice(100)).toBe(true)
    expect(validPrice(0)).toBe(false)
    expect(validPrice(-99)).toBe(false)
    expect(validPrice(50)).toBe(false)
  })
})

describe('summary', () => {
  it('counts W-L-P, stake, profit, ROI and the moneyline CLV, leaving open bets out of the return', () => {
    const games = new Map([
      ['g1', game(24, 20, { p_home: 0.7 })],
      ['g2', game(null, null, { p_home: 0.5 })],
    ])
    const s = summarize(
      [bet({ id: 'a', price: -200, stake: 10 }), bet({ id: 'b', game_id: 'g1', side: 'away', price: 100, stake: 10 }), bet({ id: 'c', game_id: 'g2' })],
      games,
    )
    expect(s).toMatchObject({ bets: 3, open: 1, wins: 1, losses: 1, pushes: 0, staked: 20 })
    expect(s.profit).toBeCloseTo(5 - 10)
    expect(s.roi).toBeCloseTo(-0.25)
    expect(s.avgClvMl).not.toBeNull()
  })

  it('has no ROI before anything settles', () => {
    expect(summarize([], new Map()).roi).toBeNull()
  })
})

describe('the stored log', () => {
  beforeEach(() => {
    localStorage.clear()
    resetBetsCache()
  })

  it('adds and deletes, and survives a reload from storage', () => {
    addBet(bet({ id: 'x' }))
    addBet(bet({ id: 'y' }))
    resetBetsCache()
    expect(getBets().map((e) => e.id)).toEqual(['x', 'y'])
    deleteBet('x')
    resetBetsCache()
    expect(getBets().map((e) => e.id)).toEqual(['y'])
  })

  it('starts empty on a corrupt value', () => {
    localStorage.setItem(BETS_KEY, '{nope')
    resetBetsCache()
    expect(getBets()).toEqual([])
  })

  it('drops malformed rows on load', () => {
    localStorage.setItem(BETS_KEY, JSON.stringify([bet({ id: 'ok' }), { id: 'bad' }]))
    resetBetsCache()
    expect(getBets().map((e) => e.id)).toEqual(['ok'])
  })
})

describe('import and export', () => {
  it('merges by id, replacing a row with the same id, and skips malformed rows', () => {
    const current = [bet({ id: 'a', stake: 10 }), bet({ id: 'b' })]
    const text = JSON.stringify([bet({ id: 'a', stake: 25 }), bet({ id: 'c' }), { id: 'broken', price: 0 }, 'junk', bet({ id: 'd', price: -50 })])
    const { next, added, skipped } = mergeImport(current, text)
    expect(added).toBe(1)
    expect(skipped).toBe(3)
    expect(next.map((e) => e.id)).toEqual(['a', 'b', 'c'])
    expect(next[0].stake).toBe(25)
  })

  it('leaves the log alone for text that is not a list', () => {
    const current = [bet()]
    expect(mergeImport(current, 'not json').next).toBe(current)
    expect(mergeImport(current, '{"a":1}').next).toBe(current)
  })

  it('accepts a {bets: []} wrapper and writes through the store', () => {
    localStorage.clear()
    resetBetsCache()
    expect(importBets(JSON.stringify({ bets: [bet({ id: 'w' })] }))).toEqual({ added: 1, skipped: 0 })
    expect(getBets().map((e) => e.id)).toEqual(['w'])
  })

  it('fills defaults when parsing', () => {
    const e = parseEntry({ id: 'z', game_id: 'g', market: 'ml', side: 'away', price: 120, stake: 5, placed_at: '2026-11-14T12:00:00Z' })
    expect(e).toMatchObject({ fee: 0, venue: '', line: null })
    expect(parseEntry({ id: 'z', game_id: 'g', market: 'spread', side: 'away', price: 120, stake: 5, placed_at: '2026-11-14T12:00:00Z' })).toBeNull() // no line
    expect(parseEntry({ id: 'z', game_id: 'g', market: 'total', side: 'home', line: 40, price: 120, stake: 5, placed_at: '2026-11-14T12:00:00Z' })).toBeNull() // wrong side
  })

  it('writes CSV with quoting', () => {
    const csv = toCsv([bet({ id: 'q', venue: 'Poly, "US"', note: 'line\nbreak' })])
    expect(csv.split('\n')[0]).toBe('id,game_id,market,side,line,price,stake,fee,venue,placed_at,note')
    expect(csv).toContain('"Poly, ""US"""')
    expect(csv).toContain('"line\nbreak"')
  })
})
