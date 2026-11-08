import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { TeamFile, type TeamMetric } from '../../data/contract'
import { biggestChange, callerChange, changeLine, leanText, placeOf, read, sortRows, starterLines, unitLine, weekList } from './tendencies'

const load = (c: string) => TeamFile.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, `../../test/fixtures/site/team/${c}.json`), 'utf8')))

const row = (now: number | null, past: number | null, last: number | null, o: Partial<TeamMetric> = {}): TeamMetric => ({
  metric: 'm', label: 'Motion', help: 'h', unit: 'pct', lo: 'less', hi: 'more', expected: null, caller_seasons: 4, caller_teams: [],
  caller_past: past == null ? null : { pct: past, seasons: 4, first: 2022 }, lean: null,
  team_last: last == null ? null : { season: 2025, pct: last, rate: 0.5, rank: 22, of: 32 },
  observed: now == null ? null : { pct: now, rate: 0.7, n: 400, rank: 3, of: 32 }, ...o,
})

describe('read', () => {
  it('says which past this season looks like', () => {
    expect(read(row(0.9, 0.95, 0.3))).toBe('past')
    expect(read(row(0.3, 0.95, 0.35))).toBe('last')
    expect(read(row(0.5, 0.55, 0.45))).toBe('both')
    expect(read(row(0.9, 0.2, 0.3))).toBe('neither')
  })
  it('compares with last season alone when the caller has no past', () => {
    expect(read(row(0.4, null, 0.45))).toBe('steady')
    expect(read(row(0.9, null, 0.3))).toBe('changed')
  })
  it('has nothing to say without this season', () => {
    expect(read(row(null, 0.9, 0.3))).toBeNull()
  })
  it('puts the new first', () => {
    const rows = [row(0.5, 0.55, 0.45, { metric: 'a', label: 'A' }), row(0.9, 0.2, 0.3, { metric: 'b', label: 'B' }), row(0.9, 0.95, 0.3, { metric: 'c', label: 'C' })]
    expect(sortRows(rows).map((r) => r.metric)).toEqual(['b', 'c', 'a'])
  })
})

describe('words', () => {
  it('says which mark to watch only where the study says so', () => {
    expect(leanText(row(null, 0.9, 0.3, { lean: 'caller' }))).toBe('Watch the caller')
    expect(leanText(row(null, 0.9, 0.3, { lean: null }))).toBeNull()
  })
  it('counts both comparisons, naming a confirmed caller only', () => {
    const caller = { name: 'Ann', confirmed: true, is_head_coach: false, evidence: 'news', source_url: null, situation: null, situation_text: null, career: [], traits: [] }
    const live = [row(0.9, 0.95, 0.3), row(0.3, 0.95, 0.35), row(0.5, 0.55, 0.45)]
    expect(unitLine({ caller, live, charted: [] }, 'AAA')).toBe("Looks like Ann's past on 2 of 3 measures, and like last year's AAA on 2 of 3.")
    expect(unitLine({ caller: { ...caller, confirmed: false }, live, charted: [] }, 'AAA')).not.toContain('Ann')
    expect(unitLine({ caller, live: [row(0.4, null, 0.45)], charted: [] }, 'AAA')).toBe("No confirmed play-calling past, so vs last year's AAA: same on 1 of 1.")
  })
  it('counts the past only over measures that have one', () => {
    const caller = { name: 'Ann', confirmed: true, is_head_coach: false, evidence: 'news', source_url: null, situation: null, situation_text: null, career: [], traits: [] }
    const live = [row(0.9, 0.95, 0.3), row(0.5, null, 0.45), row(0.2, null, 0.6)]
    expect(unitLine({ caller, live, charted: [] }, 'AAA')).toBe("Looks like Ann's past on 1 of 1 measures, and like last year's AAA on 1 of 3.")
  })
  it('explains a mid-season change', () => {
    const c = { role: 'OFF_PC', name: 'Payton', start_week: 5, end_week: null, evidence: 'news', confirmed: true, source_url: null, replaced: 'Webb' }
    expect(changeLine(c, 8)).toBe('Weeks 1–4 were called by Webb, so these numbers mix two callers.')
    expect(changeLine({ ...c, start_week: 9 }, 8)).toContain('called by someone else')
    expect(callerChange(load('CAR'), 'def')?.name).toBe('Todd Wash')
  })
  it('finds the biggest move from last season, and nothing small', () => {
    const f = load('LAC')
    const moves = f.units.off.live.concat(f.units.def.live).filter((m) => m.observed && m.team_last).map((m) => [m.metric, Math.abs(m.observed!.pct - m.team_last!.pct)] as const)
    const top = moves.reduce((a, b) => (b[1] > a[1] ? b : a))
    expect(biggestChange(f)?.metric).toBe(top[0])
    const calm = { ...f, units: { off: { ...f.units.off, live: [row(0.5, null, 0.45)] }, def: { ...f.units.def, live: [] } } }
    expect(biggestChange(calm)).toBeNull()
  })
  it('turns a share into a place', () => {
    expect(placeOf(0.98)).toBe(1)
    expect(placeOf(0.5)).toBe(17) // 16.5 rounds up: the middle of 32
    expect(placeOf(0.02)).toBe(32)
  })
  it('joins weeks and names other starters', () => {
    expect(weekList([2, 3, 4, 7])).toBe('Weeks 2–4, 7')
    const f = { ...load('LAC'), other_starter_weeks: [{ week: 2, qb: 'Drew Lock' }, { week: 3, qb: 'Drew Lock' }] }
    expect(starterLines(f)).toEqual(['Drew Lock started Weeks 2–3.'])
  })
})
