import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { TeamAccent } from './TeamAccent'
import { teamInfo } from '../lib/teams'

describe('TeamAccent', () => {
  it('draws a 3px bar in the team color, gray for unknown codes', () => {
    const { container, rerender } = render(<TeamAccent team="GB" />)
    const bar = container.firstElementChild as HTMLElement
    expect(bar.className).toContain('h-[3px]')
    expect(bar.style.background).not.toBe('')
    expect(bar.dataset.team).toBe('GB')
    rerender(<TeamAccent team="ZZZ" />)
    expect((container.firstElementChild as HTMLElement).style.background).toBe('rgb(138, 137, 132)')
  })
})

describe('teamInfo', () => {
  it('covers 32 franchises and aliases historical codes', () => {
    const codes = 'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(' ')
    expect(codes).toHaveLength(32)
    for (const c of codes) expect(teamInfo(c).color).toMatch(/^#[0-9A-F]{6}$/i)
    expect(teamInfo('STL')).toEqual(teamInfo('LA'))
    expect(teamInfo('LAR')).toEqual(teamInfo('LA'))
    expect(teamInfo('SD')).toEqual(teamInfo('LAC'))
    expect(teamInfo('OAK')).toEqual(teamInfo('LV'))
    expect(teamInfo('GB').name).toBe('Green Bay Packers')
    expect(teamInfo(undefined).color).toBe('#8a8984')
  })
})
