import { describe, expect, it } from 'vitest'
import fixture from '../../test/fixtures/site/teams.json'
import { DEFAULT_PRESET, PRESETS, presetFor } from './presets'

describe('presets', () => {
  it('has the eight presets, preset 1 first and the default', () => {
    expect(PRESETS).toHaveLength(8)
    expect(DEFAULT_PRESET.id).toBe('offense-defense')
    expect(new Set(PRESETS.map((p) => p.id)).size).toBe(8)
  })

  it('uses only feature ids that exist in the fixture, each with four captions', () => {
    const ids = new Set(fixture.features.map((f) => f.id))
    for (const p of PRESETS) {
      expect(ids.has(p.x), p.x).toBe(true)
      expect(ids.has(p.y), p.y).toBe(true)
      expect(p.quadrants).toHaveLength(4)
    }
  })

  it('finds a preset by its pair, in order', () => {
    expect(presetFor('strength.epa_off', 'strength.epa_def')?.id).toBe('offense-defense')
    expect(presetFor('strength.epa_def', 'strength.epa_off')).toBeUndefined()
  })
})
