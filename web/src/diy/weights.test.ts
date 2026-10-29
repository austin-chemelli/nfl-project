import { describe, expect, it } from 'vitest'
import { capMarket, decodeWeights, encodeWeights, fmtG, normalize } from './weights'
import { pointsFromWeights } from './weightSets'

describe('share string', () => {
  it('round-trips and drops zeros', () => {
    const w = { quality: 30, form: -10.5, buzz: 0, market: 5 }
    const s = encodeWeights(w)
    expect(s).toBe('quality:30,form:-10.5,market:5')
    expect(decodeWeights(s)).toEqual({ quality: 30, form: -10.5, market: 5 })
  })
  it('ignores junk and clamps to +-100', () => {
    expect(decodeWeights('quality:300,nope:1,form:x,health:-2e2,,stakes')).toEqual({ quality: 100, health: -100 })
    expect(decodeWeights(null)).toEqual({})
  })
  it("formats like Python's %g", () => {
    expect(fmtG(33.3333333)).toBe('33.3333')
    expect(fmtG(1e-5)).toBe('1e-05')
    expect(fmtG(0.0001)).toBe('0.0001')
    expect(fmtG(100)).toBe('100')
    expect(fmtG(-7.25)).toBe('-7.25')
    expect(fmtG(123456789)).toBe('1.23457e+08')
  })
})

describe('market cap and normalization', () => {
  it('caps the market group at 20% of the budget', () => {
    const [w, hit] = capMarket({ quality: 80, market: 60 })
    expect(hit).toBe(true)
    expect(w.market).toBeCloseTo(20)
    const n = normalize({ quality: 80, market: 60 })
    expect(Math.abs(n.weights.market)).toBeCloseTo(0.2)
    expect(n.capped).toBe(true)
  })
  it('scales points so the top weight is 100', () => {
    expect(pointsFromWeights({ quality: 0.1, form: -0.05, buzz: 0.3 }, ['quality', 'form'])).toEqual({ quality: 100, form: -50 })
  })
})
