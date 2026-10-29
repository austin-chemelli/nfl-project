import { describe, expect, it } from 'vitest'
import { consistencyText, lastStint, metricsFor, pct0, pctWords, personLabel, searchPeople, trendRows, type MetricDef, type Person, type Season } from './helpers'

const shotgun = { side: 'off', label: 'Shotgun', kind: 'scheme', noun: 'shotgun', hi: 'more', lo: 'less', help: '', unit: 'pct' } as MetricDef
const season = (n: number, team: string, rate: number | null): Season =>
  ({ season: n, team, source: 'play_caller', partial: false, qb: null, metrics: { shotgun_share: { rate, pct: 0.5, n: 10, league: 0.6 } } }) as Season

describe('percentile words', () => {
  it('phrases high, low and middle', () => {
    expect(pctWords(0.88, shotgun)).toBe('more shotgun than 88% of the league')
    expect(pctWords(0.1, shotgun)).toBe('less shotgun than 90% of the league')
    expect(pctWords(0.5, shotgun)).toBe('near the league average in shotgun')
    expect(pctWords(null, shotgun)).toBe('not enough charted plays')
    expect(pct0(0.534)).toBe('53%')
    expect(pct0(null)).toBe('–')
  })
  it('capitalizes consistency or says too early', () => {
    expect(consistencyText('changes a lot')).toBe('Changes a lot')
    expect(consistencyText(null)).toBe('Too early')
  })
})

describe('people and trends', () => {
  const p = (name: string, seasons: Season[]): Person => ({ name, sides: [{ side: 'off', role: 'x', seasons, summary: null }] }) as Person
  it('labels with the last stint and searches by name', () => {
    const a = p('Adam Gase', [season(2016, 'MIA', 0.6), season(2019, 'NYJ', 0.5)])
    expect(lastStint(a)).toEqual({ team: 'NYJ', season: 2019 })
    expect(personLabel(a)).toBe('Adam Gase (last: NYJ 2019)')
    expect(personLabel(p('No Data', []))).toBe('No Data')
    expect(searchPeople([a, p('Bo', [])], 'gas')).toHaveLength(1)
  })
  it('prefers the league table and falls back to the season value', () => {
    const rows = trendRows([season(2016, 'MIA', 0.7), season(2017, 'MIA', null)], { '2016': { off: { shotgun_share: 0.65 } } }, 'off', 'shotgun_share')
    expect(rows[0]).toMatchObject({ label: '2016 MIA', rate: 0.7, league: 0.65 })
    expect(rows[1]).toMatchObject({ rate: null, league: 0.6 })
  })
  it('filters metrics by side and kind', () => {
    const m = { a: { ...shotgun }, b: { ...shotgun, kind: 'result' }, c: { ...shotgun, side: 'def' } } as Record<string, MetricDef>
    expect(metricsFor(m, 'off', 'scheme').map(([k]) => k)).toEqual(['a'])
    expect(metricsFor(m, 'off').map(([k]) => k)).toEqual(['a', 'b'])
  })
})
