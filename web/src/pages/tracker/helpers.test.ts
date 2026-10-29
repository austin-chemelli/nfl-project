import { describe, expect, it } from 'vitest'
import {
  calibrationScaleSentence, calibrationVerdict, currentSummary, divergenceSentence, foldReliability,
  headlineSentence, marketWinsWhenApart, personaHistoryHeadline, shortName,
} from './helpers'

const rel = (mean_p: number, hit_rate: number, n: number) => ({ model_id: 'x', bin: 0, mean_p, hit_rate, n })

describe('foldReliability', () => {
  it('pools mirrored bins into the favored side', () => {
    const out = foldReliability([rel(0.25, 0.3, 100), rel(0.75, 0.7, 100)])
    expect(out).toHaveLength(1)
    expect(out[0].mean_p).toBeCloseTo(0.75)
    expect(out[0].hit_rate).toBeCloseTo(0.7)
    expect(out[0].n).toBe(200)
  })
})

describe('calibrationVerdict', () => {
  it('flags overconfidence in points', () => {
    const v = calibrationVerdict([rel(0.7, 0.62, 400)], 'The Sharp')
    expect(v.kind).toBe('over')
    expect(v.text).toContain('overconfident by 8 points')
  })
  it('flags underconfidence', () => {
    expect(calibrationVerdict([rel(0.7, 0.78, 400)], 'X').kind).toBe('under')
  })
  it('says well calibrated within 3 points', () => {
    expect(calibrationVerdict([rel(0.7, 0.71, 400)], 'X').text).toContain('well calibrated')
  })
  it('refuses to judge a thin sample', () => {
    expect(calibrationVerdict([rel(0.7, 0.9, 10)], 'X').kind).toBe('few')
  })
})

describe('divergenceSentence', () => {
  it('matches the copy in the feedback doc', () => {
    expect(divergenceSentence({ bucket: '10+', n: 1158, lean_win_rate: 0.4, market_expected_rate: 0.42 }, 'the Traditionalist')).toBe(
      'In 1,158 games where the Traditionalist disagreed with the market by 10+ points, its side won 40% of the time; the market expected 42%.',
    )
  })
  it('counts market wins in the 5+ buckets', () => {
    const d = (bucket: string, m: number, k: number) => ({ model_id: 'a', bucket, n: 1, lean_win_rate: 0.4, market_expected_rate: 0.4, model_log_loss: m, market_log_loss: k })
    expect(marketWinsWhenApart([d('10+', 0.7, 0.6), d('5-10', 0.5, 0.6), d('0-2.5', 0.7, 0.6)])).toEqual([1, 2])
  })
})

describe('persona helpers', () => {
  const a = { name: 'The Analyst', persona_share: { form: 15, offense: 20 }, history_share: { form: 6, offense: 21 }, history_shifted_points: 8.7 } as never
  it('names the biggest gap', () => {
    expect(personaHistoryHeadline(a, (k) => (k === 'form' ? 'Form' : k))).toBe("History would move 9 of the Analyst's 100 attention points; the biggest gap: Form, 15 vs 6.")
  })
  it('shortens names and describes the scale', () => {
    expect(shortName('The Analyst')).toBe('the Analyst')
    expect(calibrationScaleSentence(0.8)).toContain('25% more confident')
    expect(calibrationScaleSentence(1)).toContain('no rescaling')
  })
})

describe('headline', () => {
  const cur = [
    { model_id: 'analyst', week: 1, n: 16, cum_log_loss: 0.65, live: false },
    { model_id: 'analyst', week: 2, n: 14, cum_log_loss: 0.64, live: false },
    { model_id: 'market_baseline', week: 1, n: 16, cum_log_loss: 0.62, live: false },
    { model_id: 'market_baseline', week: 2, n: 14, cum_log_loss: 0.6, live: false },
  ]
  it('compares to the market after N games', () => {
    const s = currentSummary(cur)
    expect(s.liveGames).toBe(0)
    const row = s.rows.find((r) => r.model_id === 'analyst')!
    expect(headlineSentence(row, 'the Analyst')).toBe('After 30 games, the Analyst is 0.040 worse than the market (log loss; lower is better).')
  })
})
