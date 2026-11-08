import { describe, expect, it } from 'vitest'
import type { Game } from '../../data/contract'
import { gridTicks, valueDomain } from '../../charts/LinePath'
import { eventGroups, hasLine } from './TheLine'

type Ev = Game['market_events'][number]
const ev = (after: number, text: string): Ev => ({ ts: '2026-11-01T00:00:00Z', kind: 'game', team: 'DET', text, source_url: null, after })

describe('The line', () => {
  it('numbers only events between two snapshots; earlier and later ones are listed apart', () => {
    const g = eventGroups([ev(-1, 'before'), ev(0, 'first move'), ev(6, 'last move'), ev(7, 'after the latest')], 8)
    expect(g.between.map((e) => e.text)).toEqual(['first move', 'last move'])
    expect(g.before.map((e) => e.text)).toEqual(['before'])
    expect(g.after.map((e) => e.text)).toEqual(['after the latest'])
  })

  it('the scale zooms to the line and our number, and takes in pick\'em only when the line is near it', () => {
    const [lo, hi] = valueDomain([-7, -7.25], -8.8, true)
    expect(lo).toBeLessThan(-8.8)
    expect(hi).toBeLessThan(-6.5) // DET −7: pick'em stays off, so a quarter-point step is visible
    const [nlo, nhi] = valueDomain([-2.75, -3], null, true)
    expect(nhi).toBeGreaterThan(0) // CIN −3: within 3 points, pick'em is drawn
    expect(nlo).toBeLessThan(-3)
    const [flo, fhi] = valueDomain([48.5, 48.5], null, false)
    expect(fhi - flo).toBeGreaterThanOrEqual(2) // a flat line still gets a readable span
  })

  it('gridlines land on round values', () => {
    expect(gridTicks([-9.1, -6.6])).toEqual([-9, -8.5, -8, -7.5, -7])
    expect(gridTicks([44, 53])).toEqual([44, 46, 48, 50, 52])
  })
})

describe('hasLine', () => {
  it('needs two snapshots and a move summary', () => {
    const p = { ts: '2026-11-01T00:00:00Z', spread_home: -3, total: 45, p_home: 0.4, n_books: 6 }
    expect(hasLine({ market_history: [], line_move: null } as unknown as Game)).toBe(false)
    expect(hasLine({ market_history: [p], line_move: {} } as unknown as Game)).toBe(false)
    expect(hasLine({ market_history: [p, p], line_move: {} } as unknown as Game)).toBe(true)
  })
})
