import { describe, expect, it } from 'vitest'
import { bestWorst, chartRows, filterFeatures, itemOptions, pp, resolveItem, searchOptions, skillText, sortFeatures, UNGROUPED, verdictCounts, type Feature, type Item } from './helpers'

const f = (o: Partial<Feature>): Feature =>
  ({ feature: 'a.b', label: 'B', group: 'quality', verdict: 'matters', effect_pp: 1, effect_lo_pp: 0, effect_hi_pp: 2, marginal_pp: 1, sentence: '', coverage: '', personas: [], ...o }) as Feature
const name = (id: string) => (id === 'quality' ? 'Quality' : undefined)

const item = (o: Partial<Item>): Item =>
  ({ kind: 'feature', label: 'X', pooled: { n_games: 1, edge_win_rate: 0.5, improvement: 0 }, series: [], sentence: '', ...o }) as Item
const pt = (season: number, skill: number | null, edge: number | null = 0.5) => ({ season, n_games: 10, n_edge: 8, edge_win_rate: edge, improvement: 0, skill_pct: skill })

describe('feature helpers', () => {
  it('filters and sorts with ungrouped last', () => {
    const feats = [f({ feature: 'x', group: null, effect_pp: 5 }), f({ feature: 'y', effect_pp: 1 }), f({ feature: 'z', effect_pp: -3, verdict: 'weak' })]
    expect(sortFeatures(feats, name).map((x) => x.feature)).toEqual(['z', 'y', 'x'])
    expect(filterFeatures(feats, name, UNGROUPED, '')).toHaveLength(1)
    expect(filterFeatures(feats, name, 'Quality', 'weak').map((x) => x.feature)).toEqual(['z'])
    expect(verdictCounts(feats)).toEqual({ matters: 2, weak: 1, 'no evidence': 0 })
  })
  it('formats signed points', () => {
    expect(pp(1.234)).toBe('+1.23')
    expect(pp(-0.5, 1)).toBe('−0.5')
    expect(skillText(null)).toBe('–')
    expect(skillText(-0.46)).toBe('−0.5%')
  })
})

describe('over-time helpers', () => {
  const items = { 'a.f': item({ label: 'Zed' }), 'group:g': item({ kind: 'group', label: 'Gee' }), 'a.e': item({ label: 'Alpha' }) }
  it('orders groups first and searches by name', () => {
    expect(itemOptions(items).map((o) => o.key)).toEqual(['group:g', 'a.e', 'a.f'])
    expect(searchOptions(itemOptions(items), 'ALP').map((o) => o.key)).toEqual(['a.e'])
  })
  it('resolves the requested item or falls back', () => {
    expect(resolveItem(items, 'a.f')).toBe('a.f')
    expect(resolveItem(items, 'nope')).toBe('group:g')
    expect(resolveItem({ ...items, 'group:quality': item({ kind: 'group' }) }, null)).toBe('group:quality')
    expect(resolveItem({}, null)).toBeNull()
  })
  it('fills gap seasons and scales win rate to percent', () => {
    const rows = chartRows(item({ series: [pt(2012, 1, 0.6), pt(2014, -1, null)] }), 2011)
    expect(rows.map((r) => r.season)).toEqual([2011, 2012, 2013, 2014])
    expect(rows[1].edge).toBeCloseTo(60)
    expect(rows[0].edge).toBeNull()
    expect(rows[3].edge).toBeNull()
    expect(rows[3].skill).toBe(-1)
  })
  it('picks best and worst, preferring the file values', () => {
    const series = [pt(2012, 1), pt(2013, 3), pt(2014, -2)]
    expect(bestWorst(item({ series }))).toEqual({ best: 2013, worst: 2014 })
    expect(bestWorst(item({ series, pooled: { n_games: 1, edge_win_rate: 0.5, improvement: 0, best_season: 2012, worst_season: 2013 } }))).toEqual({ best: 2012, worst: 2013 })
    expect(bestWorst(item({}))).toEqual({ best: null, worst: null })
  })
})
