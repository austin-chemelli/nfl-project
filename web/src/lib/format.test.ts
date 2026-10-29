import { describe, expect, it } from 'vitest'
import { fmtUnit, llVsMarket, pct, pick, pts, ptsToward, spreadLabel } from './format'

describe('format', () => {
  it('percent and points', () => {
    expect(pct(0.634)).toBe('63%')
    expect(pct(null)).toBe('–')
    expect(pts(3.94)).toBe('+3.9 pts')
    expect(pts(-1.25)).toBe('−1.3 pts')
    expect(ptsToward(2.1, 'GB', 'CAR')).toBe('+2.1 pts toward GB')
    expect(ptsToward(-2.1, 'GB', 'CAR')).toBe('−2.1 pts toward CAR')
  })
  it('spreads and picks read like a sportsbook', () => {
    expect(spreadLabel(3.5, 'BUF', 'MIA')).toBe('BUF −3.5')
    expect(spreadLabel(-6, 'BUF', 'MIA')).toBe('MIA −6')
    expect(spreadLabel(0, 'BUF', 'MIA')).toBe("pick'em")
    expect(pick(0.36, 'BUF', 'MIA')).toBe('MIA 64%')
  })
  it('units mirror the Python formatter', () => {
    expect(fmtUnit(0.4567, 'pct')).toBe('46%')
    expect(fmtUnit(-0.0213, 'epa')).toBe('−0.021')
    expect(fmtUnit(1, 'flag')).toBe('yes')
    expect(fmtUnit(null, 'pct')).toBe('–')
  })
  it('log loss always comes with the market comparison', () => {
    expect(llVsMarket(0.65, 0.63)).toBe('0.650 (0.020 worse than the market)')
  })
})
