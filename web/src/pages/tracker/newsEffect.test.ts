import { describe, expect, it } from 'vitest'
import { newsEffectText } from './newsEffect'

const e = (o: object) => ({ games: 10, moved: 4, mean_abs_pts: 1, delta_log_loss: -0.02, lo: -0.05, hi: 0.01, ...o })

describe('newsEffectText', () => {
  it('says too early when the range crosses zero', () => {
    const t = newsEffectText(e({}))
    expect(t.lede).toBe("The news moved the Student's line in 4 of 10 games, by 1.0 points on average.")
    expect(t.verdict).toContain('too early to tell')
  })
  it('names a clear gap', () => {
    expect(newsEffectText(e({ lo: -0.05, hi: -0.01 })).verdict).toContain('0.020 log loss better')
  })
  it('has nothing to judge when the news never moved a line', () => {
    const t = newsEffectText(e({ moved: 0, games: 1, mean_abs_pts: null, delta_log_loss: 0, lo: null, hi: null }))
    expect(t.lede).toContain('1 game so far')
    expect(t.verdict).toBe('Nothing to judge yet.')
  })
})
