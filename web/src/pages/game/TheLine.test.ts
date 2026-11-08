import { describe, expect, it } from 'vitest'
import type { Game } from '../../data/contract'
import { valueDomain } from '../../charts/LinePath'
import { eventGroups } from './TheLine'

type Ev = Game['market_events'][number]
const ev = (after: number, text: string): Ev => ({ ts: '2026-11-01T00:00:00Z', kind: 'game', team: 'DET', text, source_url: null, after })

describe('The line', () => {
  it('numbers only events between two snapshots; earlier and later ones are listed apart', () => {
    const g = eventGroups([ev(-1, 'before'), ev(0, 'first move'), ev(6, 'last move'), ev(7, 'after the latest')], 8)
    expect(g.between.map((e) => e.text)).toEqual(['first move', 'last move'])
    expect(g.before.map((e) => e.text)).toEqual(['before'])
    expect(g.after.map((e) => e.text)).toEqual(['after the latest'])
  })

  it('the spread scale always includes pick\'em with room on both sides, and our number', () => {
    const [lo, hi] = valueDomain([-7, -7.25], -8.8, true)
    expect(lo).toBeLessThan(-8.8)
    expect(hi).toBeGreaterThanOrEqual(1.5)
    const [tlo, thi] = valueDomain([48.75, 50.5], 47.5, false)
    expect(tlo).toBeLessThan(47.5)
    expect(thi).toBeGreaterThan(50.5)
    expect(tlo).toBeGreaterThan(0)
  })
})
