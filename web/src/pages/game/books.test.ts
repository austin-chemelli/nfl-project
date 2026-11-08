import { describe, expect, it } from 'vitest'
import type { BookLine, Books } from '../../data/contract'
import { bookName, booksSentence, disagrees, names, price } from './books'

const line = (book: string, spread_home: number, total = 45): BookLine => ({ book, spread_home, total, home_price: -110, away_price: -110, over_price: -110, under_price: -110, p_home: 0.5 })
const books = (rows: BookLine[], extra: Partial<Books>): Books => {
  const s = rows.map((r) => r.spread_home!).sort((a, b) => a - b)
  const t = rows.map((r) => r.total!).sort((a, b) => a - b)
  return { snapshot_ts: '2026-11-08T15:00:00Z', books: rows, spread: { lo: s[0], hi: s[s.length - 1], median: s[1], gap: s[s.length - 1] - s[0] }, total: { lo: t[0], hi: t[t.length - 1], median: t[1], gap: t[t.length - 1] - t[0] }, key: null, flags: [], n_stale: 0, ...extra }
}

describe('books', () => {
  it('names books the way people know them, and an unknown key as itself', () => {
    expect(bookName('draftkings')).toBe('DraftKings')
    expect(bookName('newbook')).toBe('newbook')
    expect(names([line('a', 1), line('fanduel', 1), line('betmgm', 1), line('bovada', 1)])).toBe('a, FanDuel and 2 more')
  })
  it('says the books split on the favorite when they straddle pick\'em', () => {
    const b = books([line('draftkings', -1.5), line('lowvig', 0), line('fanduel', 1.5)], { key: 0, flags: ['spread_gap', 'spread_key'] })
    expect(disagrees(b)).toBe(true)
    expect(booksSentence(b, 'DEN', 'KC')).toMatch(/^The books don't agree on the favorite: KC −1.5 at DraftKings, DEN −1.5 at FanDuel\./)
  })
  it('names a key number they sit on both sides of', () => {
    const b = books([line('a', 2.5), line('b', 3), line('c', 3.5)], { key: 3, flags: ['spread_key'] })
    expect(booksSentence(b, 'GB', 'CAR')).toMatch(/both sides of 3, a key number: GB −2.5 at a, GB −3.5 at c/)
  })
  it('says the books agree when nothing is flagged', () => {
    const b = books([line('a', 3), line('b', 3), line('c', 3.5)], {})
    expect(disagrees(b)).toBe(false)
    expect(booksSentence(b, 'GB', 'CAR')).toMatch(/agree on the spread within 0.5 of a point/)
    expect(booksSentence(books([line('a', 3), line('b', 3), line('c', 3)], {}), 'GB', 'CAR')).toMatch(/^Every book has GB −3\. Every book has the total at 45\./)
  })
  it('prints American odds with a real minus', () => {
    expect(price(-110)).toBe('−110')
    expect(price(100)).toBe('+100')
    expect(price(null)).toBe('')
  })
})
