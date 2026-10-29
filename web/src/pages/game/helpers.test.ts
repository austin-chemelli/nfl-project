import { describe, expect, it } from 'vitest'
import metaJson from '../../test/fixtures/site/meta.json'
import gameJson from '../../test/fixtures/site/game/2026_08_CAR_GB.json'
import { Game, Meta } from '../../data/contract'
import { byUnit, contributionItems, dotModels, edgeRows, featureContribRows, impactMarker, injuryRank, ordinal, sortInjuries, sortMatchupNotes, tape, tendencyBlocks } from './helpers'

const meta = Meta.parse(metaJson)
const game = Game.parse(gameJson)

describe('game helpers', () => {
  it('ordinals', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 78, 88, 100].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '78th', '88th', '100th'])
  })
  it('edge sentences as percentiles, strongest first', () => {
    const { rows } = edgeRows(game.edges, meta)
    expect(rows[0].sentence).toBe(`${rows[0].favors}'s ${rows[0].name} edge is in the ${ordinal(rows[0].pct)} percentile of matchups`)
    expect(rows[0].sentence).toMatch(/^[A-Z]+'s .+ edge is in the \d+(st|nd|rd|th) percentile of matchups$/)
    expect(rows.map((r) => r.pct)).toEqual([...rows.map((r) => r.pct)].sort((a, b) => b - a))
  })
  it('contributions: home field first, then groups; features biggest first', () => {
    const cm = game.contributions.analyst
    const items = contributionItems(cm, meta)
    expect(items[0]).toMatchObject({ id: 'home_field', pp: 6.2 })
    expect(items).toHaveLength(1 + Object.keys(cm.groups).length)
    const fs = featureContribRows(cm.groups.quarterback, meta)
    expect(fs[0].feature).toBe('strength.qb_epa')
    expect(fs[0].help).not.toBe('')
  })
  it('dot models order, global hidden', () => {
    const ms = dotModels(game.models)
    expect(ms[0]).toBe('market_baseline')
    expect(ms).not.toContain('global')
    expect(ms).toContain('student')
  })
  it('tape groups by heading and formats by unit', () => {
    const t = tape(game.features, meta)
    expect(t.length).toBeGreaterThan(1)
    const all = t.flatMap((h) => h.groups.flatMap((g) => g.rows))
    expect(all.every((r) => r.home && r.away)).toBe(true)
  })
  it('tendency blocks: matchup blocks use pairs, habits use the rest', () => {
    const blocks = tendencyBlocks(game.tendencies, meta, 'all', 'GB', 'CAR')
    const titles = blocks.map((b) => b.title)
    expect(titles).toContain('CAR offense vs GB defense')
    expect(titles).toContain('GB offense vs CAR defense')
    expect(titles).toContain('Defensive habits')
    const m = blocks.find((b) => b.title === 'CAR offense vs GB defense')!
    expect(m.rows.map((r) => r.key)).toContain('pass_rate')
    expect(m.rows.map((r) => r.key)).not.toContain('blitz_rate')
    const units = byUnit(m.rows)
    expect(units.map((u) => u.unit).sort()).toEqual(['epa', 'pct'])
  })
  it('injuries: out first', () => {
    expect(injuryRank('Out')).toBe(0)
    expect(injuryRank('Questionable')).toBe(2)
    const s = sortInjuries([{ status: 'Questionable', player: 'A' }, { status: 'Out', player: 'B' }, { status: 'Doubtful', player: 'C' }])
    expect(s.map((x) => x.player)).toEqual(['B', 'C', 'A'])
  })
  it('narrative markers', () => {
    expect(impactMarker(-2)).toEqual({ arrows: '▼▼', words: 'hurts a lot' })
    expect(impactMarker(1)).toEqual({ arrows: '▲', words: 'helps' })
    expect(impactMarker(0).words).toBe('neutral')
    expect(sortMatchupNotes([{ support: 1 }, { support: 3 }])[0].support).toBe(3)
  })
})
