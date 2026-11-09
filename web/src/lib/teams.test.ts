import { describe, expect, it } from 'vitest'
import { withCodes } from './teams'

describe('withCodes', () => {
  it('swaps both teams for their codes, possessives included', () => {
    const s = "Swing plays helped both teams, Jacksonville Jaguars more: a net 2.6 toward Jacksonville Jaguars. Baltimore Ravens' offense averaged -0.35."
    expect(withCodes(s, ['JAX', 'BAL'])).toBe("Swing plays helped both teams, JAX more: a net 2.6 toward JAX. BAL's offense averaged -0.35.")
  })
  it("keeps a name ending in s's and leaves other teams alone", () => {
    expect(withCodes("Kansas City Chiefs's kicker beat the Denver Broncos", ['KC', 'LV'])).toBe("KC's kicker beat the Denver Broncos")
  })
})
