import { describe, expect, it } from 'vitest'
import { contrast, cvdDistance, distance, matchupColors, matchupVars, MIN_CVD_DISTANCE, SURFACE, teamColor, teamDot, teamDotVars } from './teamColors'

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

  it('keeps a dark, muted brand color a color: the Packers stay green, not gray', () => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(teamColor('GB').dark.slice(i, i + 2), 16))
    expect(g - Math.max(r, b)).toBeGreaterThan(15) // 8 when it was treated as a neutral
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

describe('team dots', () => {
  it('keeps the main color as the fill', () => {
    for (const t of TEAMS) expect(teamDot(t).fill).toEqual(teamColor(t))
  })
  it('draws both colors clear of the page and of each other, in both themes', () => {
    for (const t of TEAMS)
      for (const m of MODES) {
        const d = teamDot(t)
        expect(contrast(d.ring[m], SURFACE[m]), `${t} ${m}`).toBeGreaterThanOrEqual(3)
        expect(distance(d.fill[m], d.ring[m]), `${t} ${m}`).toBeGreaterThanOrEqual(12)
      }
  })
  it('tells apart the teams whose main colors are identical', () => {
    for (const [a, b] of [['DAL', 'NE'], ['ATL', 'TB'], ['CIN', 'DEN']])
      for (const m of MODES) {
        expect(teamDot(a).fill[m]).toEqual(teamDot(b).fill[m])
        expect(distance(teamDot(a).ring[m], teamDot(b).ring[m]), `${a} ${b} ${m}`).toBeGreaterThanOrEqual(15)
      }
  })
  it('fills the slots index.css reads for each theme', () => {
    const d = teamDot('KC')
    expect(teamDotVars('KC')).toMatchObject({ '--team-home-dark': d.fill.dark, '--team-away-light': d.ring.light })
  })
})
