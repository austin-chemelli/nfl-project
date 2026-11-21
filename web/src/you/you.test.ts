import { beforeEach, describe, expect, it } from 'vitest'
import lines from '../test/fixtures/diy/lines.json'
import matrixFixture from '../test/fixtures/diy/matrix.json'
import parity from '../test/fixtures/diy/parity.json'
import slate from '../test/fixtures/site/slate_2026_08.json'
import type { GameRow } from '../data/contract'
import { normalize, type MatrixInput } from '../diy'
import { slateWithYou, withYou } from './augment'
import type { YouLine } from './current'
import { calibrate, capLive, contributionOf, customLine, LIVE_CAP, probit, scoreLine, youWeights } from './line'
import { clean, clearSaved, getSaved, migrate, resetSavedCache, saveApproach, setDefault, updateSaved, YOU_KEY } from './store'

const matrix = matrixFixture as unknown as MatrixInput

describe('the browser scores a line exactly as the engine does (ADR 0034)', () => {
  // published lines (artifact weights, intercept, calibration) on this season's games, scored from
  // the composites the site publishes: the browser path must give the engine's p_home
  for (const [id, line] of Object.entries(lines.lines)) {
    it(`${id}: every game, neutral sites included`, () => {
      expect(lines.games.some((g) => g.neutral)).toBe(true)
      for (const g of lines.games) {
        const want = (line.p_home as Record<string, number>)[g.game_id]
        const got = scoreLine({ W: line.W, intercept: line.intercept, a: line.a, c: line.c }, g).p_home
        // composites are published to 4 decimals
        expect(Math.abs(got - want)).toBeLessThan(5e-4)
      }
    })
  }
  it('a neutral site has no home field: level composites score 50% there and favor the home team at home', () => {
    const l = { W: { quality: 0.5 }, intercept: 0.1, a: 1, c: 0.3 }
    const home = scoreLine(l, { neutral: false, c: { quality: 0 } })
    const neutral = scoreLine(l, { neutral: true, c: { quality: 0 } })
    expect(neutral.p_home).toBeCloseTo(0.5, 6)
    expect(home.p_home).toBeGreaterThan(0.5)
    expect(neutral.home_field).toBe(0)
  })
})

describe('calibrating a custom line', () => {
  it('matches the Python walk-forward calibration for the season after the matrix', () => {
    // parity.json's season predictions: Platt fitted on every earlier season of the same matrix
    for (const c of parity.cases.filter((x) => x.signed && x.max_season == null)) {
      const w = c.weights as unknown as Record<string, number>
      if (!Object.values(w).some((v) => v)) continue
      const season = c.season.season
      const got = calibrate(w, matrix, season)
      expect(got.a).toBeCloseTo(c.season.a, 4)
      expect(got.c).toBeCloseTo(c.season.c, 4)
    }
  })
  it('the custom line is normalized points with no intercept', () => {
    const l = customLine({ quality: 60, form: -40 }, { a: 0.9, c: 0.2 })
    expect(l.W).toEqual(normalize({ quality: 60, form: -40 }).weights)
    expect(l.intercept).toBe(0)
  })
})

describe('probit and contributions', () => {
  it('inverts the normal CDF', () => {
    expect(probit(0.5)).toBe(0)
    expect(probit(0.975)).toBeCloseTo(1.959964, 5)
    expect(probit(0.01)).toBeCloseTo(-2.326348, 5)
  })
  it('breaks a scored line into group points like site.py', () => {
    const s = scoreLine({ W: { quality: 0.6, form: 0.4 }, intercept: 0, a: 1.2, c: 0.15 }, { neutral: false, c: { quality: 1, form: -0.5 } })
    const c = contributionOf(s)
    expect(c.p_home).toBeCloseTo(s.p_home, 4)
    expect(c.groups.quality.pp).toBeGreaterThan(0)
    expect(c.groups.form.pp).toBeLessThan(0)
    expect(c.home_field_pp).toBeGreaterThan(0)
  })
})

const YOU: YouLine = {
  name: 'You', points: { quality: 100 }, line: { W: { quality: 1 }, intercept: 0, a: 1, c: 0.1 },
  isDefault: false, savedAt: '2026-11-20T00:00:00Z', migration: { points: { quality: 100 }, dropped: [], added: [], changed: false },
}

describe('adding "you" to the data', () => {
  it('adds models.you to every game with composites, beside the published lines', () => {
    const s = slateWithYou(slate as never, YOU)
    for (const g of s.games as GameRow[]) {
      expect(g.models.you?.p_home).toBeGreaterThan(0)
      expect(g.models.student).toBeDefined()
      expect(g.models.you.status).toBe(g.models.student.status)
    }
  })
  it('leaves a game without composites, and every game when no line is saved, as published', () => {
    const g = { ...(slate.games[0] as unknown as GameRow), composites: null }
    expect(withYou(g, YOU)).toBe(g)
    expect(slateWithYou(slate as never, null)).toBe(slate)
  })
})

describe('the saved approach', () => {
  beforeEach(() => {
    localStorage.clear()
    resetSavedCache()
  })
  const base = { points: { quality: 60, form: -40 }, registry: '7', groups: ['quality', 'form', 'buzz'], calib: { key: '7-2025', a: 1, c: 0.1 } }

  it('saves one approach, renames it, makes it the default, and removes it', () => {
    saveApproach(base, new Date('2026-11-20T12:00:00Z'))
    expect(getSaved()).toMatchObject({ name: 'You', is_default: false, saved_at: '2026-11-20T12:00:00.000Z' })
    updateSaved({ name: '  My   line ' })
    setDefault(true)
    resetSavedCache()
    expect(getSaved()).toMatchObject({ name: 'My line', is_default: true, points: base.points })
    saveApproach({ ...base, points: { quality: 10 } })
    expect(getSaved()).toMatchObject({ name: 'My line', is_default: true, points: { quality: 10 } })
    clearSaved()
    expect(getSaved()).toBeNull()
    expect(localStorage.getItem(YOU_KEY)).toBeNull()
  })

  it('validates what it loads', () => {
    for (const bad of [null, 3, [], { v: 2, points: {}, registry: '7', saved_at: 'x' }, { v: 1, points: 'x', registry: '7', saved_at: 'x' }]) {
      expect(clean(bad)).toBeNull()
    }
    const ok = clean({ v: 1, registry: '7', saved_at: 't', points: { quality: 500, form: 'x', defense: -20 }, calib: { key: 'k', a: 'no', c: 1 }, name: '' })
    expect(ok).toMatchObject({ name: 'You', points: { quality: 100, defense: -20 }, calib: null, is_default: false })
    localStorage.setItem(YOU_KEY, '{not json')
    resetSavedCache()
    expect(getSaved()).toBeNull()
  })

  it('maps a saved approach onto a new registry and says what changed', () => {
    const m = migrate({ points: { quality: 50, coaching: 20, buzz: 0 }, groups: ['quality', 'coaching', 'buzz'], registry: '6' }, ['quality', 'offense', 'buzz'], '7')
    expect(m).toEqual({ points: { quality: 50, buzz: 0 }, dropped: ['coaching'], added: ['offense'], changed: true })
    expect(migrate({ points: { quality: 50 }, groups: ['quality'], registry: '7' }, ['quality', 'offense'], '7').added).toEqual([])
  })
})

describe('live-only groups in a custom line', () => {
  it('hold at most 30% of the budget together, so the calibration slope stays sane', () => {
    const [p, hit] = capLive({ quality: 2, market: 20, buzz: 78 })
    expect(hit).toBe(true)
    const w = youWeights({ quality: 2, market: 20, buzz: 78 })
    expect(Math.abs(w.market) + Math.abs(w.buzz)).toBeCloseTo(LIVE_CAP, 6)
    expect(p.market / p.buzz).toBeCloseTo(20 / 78, 6)
    expect(capLive({ quality: 80, market: 20 })[1]).toBe(false)
    // only live groups: nothing left to score
    expect(Object.values(youWeights({ buzz: 100 })).every((v) => v === 0)).toBe(true)
  })
  it('a mostly-Buzz line gets the slope of its history groups, not one blown up by Buzz', () => {
    const capped = calibrate(youWeights({ quality: 5, buzz: 95 }), matrix, 2009)
    const plain = calibrate(youWeights({ quality: 100 }), matrix, 2009)
    expect(capped.a / plain.a).toBeLessThan(1 / (1 - LIVE_CAP) + 1e-6)
  })
})
