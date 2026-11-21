import { describe, expect, it } from 'vitest'
import type { Meta } from '../data/contract'
import { isScored, splitFeature } from './scored'

const meta = {
  groups: {
    groups: [
      { id: 'offense', name: 'Offense', context_only: false, members: [{ feature: 'matchup.net_edge_pg' }] },
      { id: 'matchups', name: 'Matchups', context_only: true, members: [{ feature: 'matchup.edge_blitz' }] },
    ],
  },
} as unknown as Meta

describe('isScored', () => {
  it('is true only for members of a group in the line', () => {
    expect(isScored('matchup.net_edge_pg', meta)).toBe(true)
    expect(isScored(splitFeature('blitz'), meta)).toBe(false)
    expect(isScored('matchup.edge_unknown', meta)).toBe(false)
  })
})
