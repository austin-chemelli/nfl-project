import { describe, expect, it } from 'vitest'
import type { Game } from '../../data/contract'
import { newsLine } from './news'

const g = (news: unknown) => ({ home: 'HOU', away: 'IND', news }) as unknown as Game
const reasons = [{ label: 'QB questionable', team: 'HOU', pts: -0.5 }, { label: '2 starters ruled out', team: 'HOU', pts: -0.4 }]

describe('newsLine', () => {
  it('shows the football-only spread and the news on the favorite line, in plain words', () => {
    const l = newsLine(g({ pts: -0.9, football_only_spread: 10.2, reasons, cap_pts: 1.5 }))
    expect(l).toEqual({ football: 'HOU −10.2', news: '−0.9 for HOU', why: 'HOU QB questionable; HOU 2 starters ruled out' })
  })
  it('flips the sign when the away team is favored', () => {
    const l = newsLine(g({ pts: 0.6, football_only_spread: -3, reasons: [], cap_pts: 1.5 }))
    expect(l?.football).toBe('IND −3')
    expect(l?.news).toBe('−0.6 for IND')
  })
  it('says none when the news did not move the line, and is null without research', () => {
    expect(newsLine(g({ pts: 0, football_only_spread: 4, reasons: [], cap_pts: 1.5 }))?.news).toBe('none')
    expect(newsLine(g(null))).toBeNull()
  })
})
