import { describe, expect, it } from 'vitest'
import { cardMove, etDay, fmtPts, pathSentence, windowWords } from './line'

const move = (d: number | null) => ({ first_seen: '2026-10-27T22:46:59Z', latest: '2026-11-03T21:40:31Z', n_points: 10, lock_ts: null, since_first: d == null ? null : { spread_home: d, total: null, p_home: null, hours: 160 }, since_lock: null, last_day: null })

describe('line words', () => {
  it('names the team the line moved toward, and the day first seen in Eastern time', () => {
    expect(etDay('2026-10-27T22:46:59Z')).toBe('Tue')
    expect(cardMove(move(-12.5), 'BAL', 'JAX')).toBe('Line moved 12.5 toward JAX since Tue')
    expect(cardMove(move(2), 'BAL', 'JAX')).toBe('Line moved 2 toward BAL since Tue')
  })
  it('keeps small or unknown moves off the card', () => {
    expect(cardMove(move(0.5), 'BAL', 'JAX')).toBeNull()
    expect(cardMove(move(null), 'BAL', 'JAX')).toBeNull()
    expect(cardMove(null, 'BAL', 'JAX')).toBeNull()
  })
  it('describes the path from first to latest', () => {
    const pts = [
      { ts: 'a', spread_home: 2.5, total: 48.75, p_home: 0.56, n_books: 6 },
      { ts: 'b', spread_home: null, total: 45, p_home: null, n_books: 3 },
      { ts: 'c', spread_home: -10, total: 40.5, p_home: 0.19, n_books: 9 },
    ]
    expect(pathSentence(pts, 'BAL', 'JAX')).toBe('Spread BAL −2.5 → JAX −10 · total 48.75 → 40.5')
    expect(pathSentence(pts.slice(0, 1), 'BAL', 'JAX')).toBeNull()
  })
  it('prints half and quarter points', () => {
    expect(fmtPts(2.5)).toBe('2.5')
    expect(fmtPts(48.75)).toBe('48.75')
    expect(windowWords(0.1, 'BAL', 'JAX')).toBe('steady')
    expect(windowWords(-1.5, 'BAL', 'JAX')).toBe('1.5 toward JAX')
  })
})
