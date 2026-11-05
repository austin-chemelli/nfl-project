import { describe, expect, it } from 'vitest'
import type { Tracker } from '../../data/contract'
import { bankrollRows, betsVerdict, cellFill, noEdgeReturn, returnRows, signedPct, signedUnits } from './bets'

type Line = Tracker['ledger'][number]
const line = (model_id: string, roi: number, lo: number, hi: number, kind = 'backfill'): Line => ({
  model_id, kind, bets: 100, wins: 40, losses: 60, pushes: 0, units: 100 * roi, roi, roi_lo: lo, roi_hi: hi, no_edge_roi: -0.03, clv: null,
})
const season = (model_id: string, season: number, units: number, no_edge_units = -2, live_bets = 0) => ({ model_id, season, bets: 10, live_bets, units, no_edge_units })
const name = (id: string) => `the ${id}`

describe('bankrollRows', () => {
  it('starts at zero and runs the totals forward', () => {
    const rows = bankrollRows([season('sharp', 2006, 5), season('sharp', 2007, -2)])
    expect(rows.map((r) => r.season)).toEqual([2005, 2006, 2007])
    expect(rows.map((r) => r.sharp)).toEqual([0, 5, 3])
  })

  it('carries a line through a season it has no bets in', () => {
    const rows = bankrollRows([season('sharp', 2006, 5), season('student', 2006, 1), season('student', 2007, 1)])
    expect(rows[2].sharp).toBe(5)
  })

  it('averages the no-edge cost over the approaches, leaving the references out', () => {
    const rows = bankrollRows([season('sharp', 2006, 0, -2), season('student', 2006, 0, -4), season('home_naive', 2006, 0, -40)])
    expect(rows[1].no_edge).toBe(-3)
  })

  it('reports the live bets in a season', () => {
    const rows = bankrollRows([season('sharp', 2026, 1, -1, 7)])
    expect(rows[1].live).toBe(7)
  })

  it('is empty with no seasons', () => {
    expect(bankrollRows([])).toEqual([])
  })
})

describe('returnRows', () => {
  it('keeps the backtest with a range, best first', () => {
    const noRange = { ...line('analyst', 0.05, 0, 0), roi_lo: null }
    const rows = returnRows([line('student', -0.03, -0.06, 0), line('sharp', -0.01, -0.04, 0.02), line('sharp', 0.5, 0.1, 0.9, 'live'), noRange])
    expect(rows.map((r) => r.model_id)).toEqual(['sharp', 'student'])
    expect(rows[0].roi).toBe(-0.01)
  })
})

describe('noEdgeReturn', () => {
  it('reads the approaches only', () => {
    expect(noEdgeReturn([{ ...line('sharp', 0, 0, 0), no_edge_roi: -0.02 }, { ...line('elo_v0', 0, 0, 0), no_edge_roi: -0.5 }])).toBe(-0.02)
    expect(noEdgeReturn([])).toBeNull()
  })
})

describe('betsVerdict', () => {
  it('says when every approach lost, and that beating no edge was within the noise', () => {
    const text = betsVerdict([line('sharp', -0.012, -0.045, 0.02), line('student', -0.034, -0.067, 0)], name)
    expect(text).toBe('Every approach has lost money. The best, the sharp, is at −1.2% a bet. Betting with no edge at all costs 3.0% a bet. One of the two did better than that, none by more than the noise.')
  })

  it('does not call a profit an edge while its range reaches below break-even', () => {
    expect(betsVerdict([line('sharp', 0.01, -0.02, 0.04)], name)).toContain('The sharp is up +1.0% a bet, but its range still reaches below break-even.')
  })

  it('says so when a range clears break-even and no edge', () => {
    const text = betsVerdict([line('sharp', 0.05, 0.01, 0.09)], name)
    expect(text).toContain('its whole range clears break-even')
    expect(text).toContain('One of the one did better than that, one clearly.')
  })

  it('handles no approach beating no edge', () => {
    expect(betsVerdict([line('sharp', -0.05, -0.08, -0.02)], name)).toContain('None of the one did better than that.')
  })

  it('leaves the references out of the verdict', () => {
    expect(betsVerdict([line('elo_v0', 0.2, 0.1, 0.3), line('student', -0.03, -0.06, 0)], name)).toContain('The best, the student')
  })

  it('is empty before any bets have a range', () => {
    expect(betsVerdict([], name)).toBeNull()
  })
})

describe('formatting', () => {
  it('never shows a signed zero', () => {
    expect(signedPct(-0.00001)).toBe('0.0%')
    expect(signedUnits(-0.4)).toBe('0')
    expect(signedUnits(14.6)).toBe('+15')
    expect(signedUnits(-38)).toBe('−38')
  })

  it('fills by sign and caps the strength', () => {
    expect(cellFill(15)).toContain('--div-pos) 28%')
    expect(cellFill(-300)).toContain('--div-neg) 55%')
  })
})
