import { describe, expect, it } from 'vitest'
import { parseSnapshot, snapshotAgo, snapshotLabel, sortedShares, topNullRates } from './helpers'

describe('snapshots', () => {
  it('parses and labels a stamp', () => {
    expect(parseSnapshot('20261027T224658Z')?.toISOString()).toBe('2026-10-27T22:46:58.000Z')
    expect(snapshotLabel('20261027T224658Z')).toBe('2026-10-27 22:46 UTC')
    expect(snapshotLabel('weird')).toBe('weird')
  })
  it('says how long ago', () => {
    expect(snapshotAgo('20261027T224658Z', new Date('2026-10-28T02:46:58Z'))).toBe('4 h ago')
    expect(snapshotAgo(null)).toBe('–')
  })
})

describe('null rates', () => {
  const r = (col: string, null_rate: number, n_rows = 10) => ({ tbl: 't', season: 2020, col, n_rows, n_null: 0, null_rate })
  it('sorts highest first and drops complete columns', () => {
    const { shown, total } = topNullRates([r('a', 0), r('b', 0.2), r('c', 0.9)], 5)
    expect(shown.map((x) => x.col)).toEqual(['c', 'b'])
    expect(total).toBe(2)
  })
  it('sorts shares and drops dust', () => {
    expect(sortedShares({ a: 1, b: 30, c: 0.1 })).toEqual([['b', 30], ['a', 1]])
  })
})
