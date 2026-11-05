import { describe, expect, it } from 'vitest'
import { contrast, cvdDistance, distance, matchupColors, matchupVars, MIN_CVD_DISTANCE, SURFACE, teamColor } from './teamColors'

const TEAMS = 'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(' ')
const MODES = ['light', 'dark'] as const
const pairs = TEAMS.flatMap((a) => TEAMS.filter((h) => h !== a).map((h) => [a, h]))

describe('team colors', () => {
  it('every option a matchup can pick clears 3:1 on the page, in both themes', () => {
    for (const [a, h] of pairs) {
      const m = matchupColors(a, h)
      for (const mode of MODES) for (const c of [m.away, m.home]) expect(contrast(c[mode], SURFACE[mode]), `${a}@${h} ${mode} ${c[mode]}`).toBeGreaterThanOrEqual(3)
    }
  })

  it('all 992 matchups can be told apart, by normal and red-green colorblind vision', () => {
    for (const [a, h] of pairs) {
      const m = matchupColors(a, h)
      for (const mode of MODES) {
        expect(distance(m.away[mode], m.home[mode]), `${a}@${h} ${mode}`).toBeGreaterThanOrEqual(15)
        expect(cvdDistance(m.away[mode], m.home[mode]), `${a}@${h} ${mode}`).toBeGreaterThanOrEqual(MIN_CVD_DISTANCE)
      }
    }
  })

  it('keeps both first colors when they already work', () => {
    expect(matchupColors('CHI', 'MIN')).toEqual({ away: teamColor('CHI'), home: teamColor('MIN') })
  })

  it('splits two same-tone colors by lightness before reaching for a secondary color', () => {
    const m = matchupColors('JAX', 'BAL')
    expect(m.away).toEqual(teamColor('JAX')) // still teal, not Jacksonville's gold
    expect(m.home.dark).not.toEqual(teamColor('BAL').dark)
    expect(distance(m.home.dark, teamColor('BAL').dark)).toBeLessThan(20) // still purple
  })

  it('separates the teams that share a navy, the away team giving way first', () => {
    const m = matchupColors('DAL', 'NE')
    expect(m.home).toEqual(teamColor('NE'))
    expect(m.away).not.toEqual(teamColor('DAL'))
  })

  it('reads old codes as their franchise and survives an unknown one', () => {
    expect(teamColor('OAK')).toEqual(teamColor('LV'))
    expect(teamColor('STL')).toEqual(teamColor('LA'))
    expect(matchupColors('XXX', 'BAL').away.dark).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('hands both themes to the CSS', () => {
    expect(Object.keys(matchupVars('JAX', 'BAL'))).toEqual(['--team-away-light', '--team-away-dark', '--team-home-light', '--team-home-dark'])
  })
})
