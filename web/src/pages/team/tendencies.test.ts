import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { TeamFile, type TeamMetric } from '../../data/contract'
import { NOTABLE, basis, callerChange, changeLine, distance, expectWords, fmtRate, furthest, sortRows, starterLines, unitLine, verdict, weekList } from './tendencies'

const load = (c: string) => TeamFile.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, `../../test/fixtures/site/team/${c}.json`), 'utf8')))

const row = (o: Partial<TeamMetric> = {}, pct = 0.5, miss: number | null = 0.2, strength: 'fair' | 'weak' = 'fair', seen: number | null = 0.5): TeamMetric => ({
  metric: 'm', label: 'Motion', help: 'h', unit: 'pct', lo: 'less', hi: 'more',
  expected: { pct, miss, weight_on_caller: 0.6, strength }, caller_seasons: 4, caller_teams: ['MIA'],
  team_last: { season: 2025, pct: 0.3, rate: 0.5, rank: 22, of: 32 },
  observed: seen == null ? null : { pct: seen, rate: 0.7, n: 400, rank: 3, of: 32 }, ...o,
})

describe('verdict', () => {
  it('reads the edges of the range as expected', () => {
    expect(verdict(row({}, 0.5, 0.2, 'fair', 0.7))).toBe('as_expected')
    expect(verdict(row({}, 0.5, 0.2, 'fair', 0.3))).toBe('as_expected')
  })
  it('holds the upper edge past float error', () => {
    expect(verdict(row({}, 0.6, 0.2, 'fair', 0.8))).toBe('as_expected')
  })
  it('gives no verdict on a unit that changed callers', () => {
    expect(verdict(row({}, 0.2, 0.1, 'fair', 0.9), true)).toBe('mixed')
    expect(distance(row({}, 0.2, 0.1, 'fair', 0.9), true)).toBe(0)
  })
  it('says more or less only outside the range', () => {
    expect(verdict(row({}, 0.5, 0.2, 'fair', 0.71))).toBe('more')
    expect(verdict(row({}, 0.5, 0.2, 'fair', 0.29))).toBe('less')
  })
  it('never judges a weak row', () => {
    expect(verdict(row({}, 0.5, 0.2, 'weak', 0.99))).toBe('rough')
  })
  it('has nothing to say without a miss or an expected value', () => {
    expect(verdict(row({}, 0.5, null))).toBe('no_range')
    expect(verdict(row({ expected: null }))).toBe('no_range')
  })
  it('waits on a charted row with no observed value yet', () => {
    expect(verdict(row({}, 0.5, 0.2, 'fair', null))).toBe('waiting')
  })
})

describe('order and the tile', () => {
  it('puts surprises first and rough guesses after', () => {
    const rough = row({ metric: 'a', label: 'A' }, 0.5, 0.2, 'weak', 0.99)
    const fine = row({ metric: 'b', label: 'B' }, 0.5, 0.2, 'fair', 0.5)
    const big = row({ metric: 'c', label: 'C' }, 0.2, 0.1, 'fair', 0.9)
    const small = row({ metric: 'd', label: 'D' }, 0.5, 0.2, 'fair', 0.75)
    expect(sortRows([rough, fine, small, big]).map((r) => r.metric)).toEqual(['c', 'd', 'b', 'a'])
    expect(distance(rough)).toBe(0)
  })
  it('the tile only ever names a row outside its range', () => {
    for (const code of ['LAC', 'CAR']) {
      const top = furthest(load(code))
      if (top) expect(['more', 'less']).toContain(verdict(top.row))
    }
  })
  it('has no line when nothing clears its range', () => {
    expect(unitLine({ caller: null, live: [row()], charted: [] })).toBeNull()
  })
  it('only calls out a row well outside its range', () => {
    const caller = null
    expect(unitLine({ caller, live: [row({}, 0.5, 0.2, 'fair', 0.75)], charted: [] })).toBeNull()
    const far = 0.5 + 0.2 * NOTABLE + 0.01
    expect(unitLine({ caller, live: [row({}, 0.5, 0.2, 'fair', far)], charted: [] })).toContain('above what last season suggested')
  })
  it('names only the sources the expected value used', () => {
    const caller = { name: 'Ann', confirmed: true, is_head_coach: false, evidence: 'news', source_url: null, situation: null, situation_text: null, career: [] }
    const at = (w: number) => { const r = row({}, 0.2, 0.1, 'fair', 0.9); r.expected!.weight_on_caller = w; return unitLine({ caller, live: [r], charted: [] }) }
    expect(at(0)).toContain('what last season suggested')
    expect(at(0)).not.toContain('Ann')
    expect(at(1)).toContain("what Ann's past suggested")
    expect(at(0.6)).toContain("Ann's past and last season")
  })
  it('explains a mid-season change, and a caller who has not coached yet', () => {
    const c = { role: 'OFF_PC', name: 'Payton', start_week: 5, end_week: null, evidence: 'news', confirmed: true, source_url: null, replaced: 'Webb' }
    expect(changeLine(c, 8)).toBe('Weeks 1–4 were called by Webb, so these rates mix two callers.')
    expect(changeLine({ ...c, replaced: null }, 8)).toBe('Payton took over in Week 5, so these rates mix two callers.')
    expect(changeLine({ ...c, start_week: 9 }, 8)).toContain('these games were called by someone else')
    expect(changeLine({ ...c, start_week: 2 }, 8)).toContain('Week 1 ')
  })
  it('skips a unit that changed callers for the tile', () => {
    const f = load('CAR')
    expect(callerChange(f, 'def')?.name).toBe('Todd Wash')
    expect(furthest(f)?.side).not.toBe('def')
  })
  it('names a confirmed caller only', () => {
    const caller = { name: 'Ann', confirmed: true, is_head_coach: false, evidence: 'news', source_url: null, situation: null, situation_text: null, career: [] }
    const live = [row({}, 0.2, 0.1, 'fair', 0.9)]
    expect(unitLine({ caller, live, charted: [] })).toContain("Ann's past")
    expect(unitLine({ caller: { ...caller, confirmed: false }, live, charted: [] })).not.toContain('Ann')
  })
})

describe('words', () => {
  it('turns a prediction into words, with the metric\'s own ends', () => {
    expect(expectWords(row({ lo: 'shorter', hi: 'longer' }, 0.8))).toEqual(['Longer', 'than most'])
    expect(expectWords(row({ lo: 'shorter', hi: 'longer' }, 0.2))).toEqual(['Shorter', 'than most'])
    expect(expectWords(row({}, 0.5))).toEqual(['About', 'average'])
  })
  it('says where expected came from', () => {
    const f = load('LAC')
    expect(basis(row(), f, 'Mike McDaniel')).toBe("From 4 seasons of Mike McDaniel's past and LAC's 2025")
    expect(basis(row({ caller_seasons: 0 }), f, 'New Guy')).toBe("From LAC's 2025 alone")
  })
  it('prints rates by unit', () => {
    expect(fmtRate(0.738, 'pct')).toBe('73.8%')
    expect(fmtRate(2.71, 'seconds')).toBe('2.71 s')
  })
  it('joins weeks into runs', () => {
    expect(weekList([2, 3, 4, 7])).toBe('Weeks 2–4, 7')
    expect(weekList([5])).toBe('Week 5')
  })
  it('lists other starters by name', () => {
    const f = { ...load('LAC'), other_starter_weeks: [{ week: 2, qb: 'Drew Lock' }, { week: 3, qb: 'Drew Lock' }] }
    expect(starterLines(f)).toEqual(['Drew Lock started Weeks 2–3.'])
  })
})
