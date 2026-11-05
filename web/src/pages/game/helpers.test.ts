import { describe, expect, it } from 'vitest'
import metaJson from '../../test/fixtures/site/meta.json'
import gameJson from '../../test/fixtures/site/game/2026_08_CAR_GB.json'
import { Game, Meta, RetroGame } from '../../data/contract'
import { byUnit, contributionItems, dotModels, edgeRows, featureContribRows, impactMarker, injuryRank, lineMoveChip, ordinal, phaseSummary, playedLikeSteps, previewRows, sortInjuries, sortMatchupNotes, swingRows, tape, tendencyBlocks } from './helpers'

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

describe('context-only groups', () => {
  it('are not edges, in the list or the summary tile', () => {
    const edges = { coaching: { favors: 'GB', strength_pct: 99 }, quality: { favors: 'GB', strength_pct: 60 }, off_scheme: { favors: null, strength_pct: 5 } }
    const { rows, none } = edgeRows(edges, meta)
    expect(rows.map((r) => r.id)).toEqual(['quality'])
    expect(none).toEqual([])
  })
})

describe('previewRows', () => {
  const pp = (v: number) => ({ pp: v, features: {} })
  const contrib = (groups: Record<string, number>, home = 5) => ({
    p_home: 0.5, home_field_pp: home, groups: Object.fromEntries(Object.entries(groups).map(([k, v]) => [k, pp(v)])),
  })
  const g = (over: Partial<Game> = {}): Game => ({
    ...game,
    neutral_site: false,
    edges: { quality: { favors: 'GB', strength_pct: 90 }, offense: { favors: 'CAR', strength_pct: 4 }, defense: { favors: null, strength_pct: 19 } },
    contributions: {
      global: contrib({ quality: 7, offense: -1, defense: 0, coaching: 2, off_scheme: 1, def_scheme: 1 }),
      sharp: contrib({ quality: 3, market: -20, buzz: 0 }, 4),
    },
    ...over,
  })
  const ids = (rows: { id: string }[]) => rows.map((r) => r.id)

  it('leads with home field, follows the registry and leaves the context-only groups out', () => {
    expect(ids(previewRows(g(), meta, null))).toEqual(['home_field', 'quality', 'offense', 'defense'])
  })
  it('reads context_only from meta, so a group can move without a change here', () => {
    const m = structuredClone(meta)
    m.groups.groups.find((x) => x.id === 'offense')!.context_only = true
    expect(ids(previewRows(g(), m, null))).not.toContain('offense')
  })
  it('labels the edge, calling a bottom-tenth or unfavored matchup even', () => {
    const [hf, quality, offense, defense] = previewRows(g(), meta, null)
    expect(hf.edge).toBe('GB at home')
    expect(quality.edge).toBe('GB, 90th pct')
    expect(offense.edge).toBe('about even')
    expect(defense.edge).toBe('about even')
    expect(previewRows(g({ neutral_site: true }), meta, null)[0].edge).toBe('neutral site')
  })
  it('overlays an approach; a group only it has gets a row unless it is zero', () => {
    const rows = previewRows(g(), meta, 'sharp')
    expect(rows[0]).toMatchObject({ pp: 5, overlay: 4 })
    expect(rows.find((r) => r.id === 'quality')).toMatchObject({ pp: 7, overlay: 3 })
    expect(rows.find((r) => r.id === 'market')).toMatchObject({ pp: null, overlay: -20 })
    expect(ids(rows)).not.toContain('buzz')
  })
  it('has no rows without the fit', () => {
    expect(previewRows(g({ contributions: {} }), meta, null)).toEqual([])
  })
})

describe('lineMoveChip', () => {
  const at = (v: number | null | undefined) => ({ ...game, features: v === undefined ? {} : { 'market.line_move_pts': { group: 'market', game: v } } }) as Game
  it('prints the raw move and its direction', () => {
    expect(lineMoveChip(at(-12.5))).toBe(`Followed a 12.5-point line move toward ${game.away}`)
    expect(lineMoveChip(at(3))).toBe(`Followed a 3-point line move toward ${game.home}`)
    expect(lineMoveChip(at(8))).toBe(`Followed an 8-point line move toward ${game.home}`)
    expect(lineMoveChip(at(11.5))).toBe(`Followed an 11.5-point line move toward ${game.home}`)
  })
  it('says nothing when the line barely moved or there is no reading', () => {
    expect(lineMoveChip(at(0.5))).toBeNull()
    expect(lineMoveChip(at(null))).toBeNull()
    expect(lineMoveChip(at(undefined))).toBeNull()
  })
})

describe('tape bands', () => {
  const m = (bands: Meta['feature_bands']) => ({ ...meta, feature_bands: bands })
  const f = 'strength.epa_off'
  const row = (home: number | null, away: number | null, meta2: Meta, feature = f) =>
    tape({ [feature]: { group: 'offense', home, away } }, meta2).flatMap((h) => h.groups.flatMap((x) => x.rows))[0]
  const band = { lo: -0.1, q1: -0.05, med: 0, q3: 0.05, hi: 0.1 }

  it('a gap stands out only past the league interquartile width', () => {
    expect(row(0.12, 0, m({ [f]: band })).band).toMatchObject({ stands: true, flip: false })
    expect(row(0.05, 0, m({ [f]: band })).band?.stands).toBe(false)
  })
  it('flips a feature where lower is better', () => {
    expect(row(0, 0, m({ 'strength.epa_def': band }), 'strength.epa_def').band?.flip).toBe(true)
  })
  it('stays a plain row with no band, a missing side, or no spread in the league', () => {
    expect(row(0.1, 0, m({})).band).toBeNull()
    expect(row(0.1, null, m({ [f]: band })).band).toBeNull()
    expect(row(0.1, 0, m({ [f]: { lo: 0, q1: 0, med: 0, q3: 0, hi: 0 } })).band).toBeNull()
  })
})

describe('swingRows', () => {
  const f = (factor: string, swing: number, skill: boolean) => ({ factor, label: factor, actual: 0, expected: 0, unit: 'count', attempts: null, swing_pts: swing, partly_skill: skill, sentence: `${factor} ${swing}` })
  const team = (name: string, luck: ReturnType<typeof f>[]) => ({ team: name, score: 0, efficiency: [], luck, luck_net: luck.reduce((a, x) => a + x.swing_pts, 0) })
  const r = {
    teams: {
      home: team('GB', [f('third_down', 8.1, true), f('kicking', -0.8, false), f('special_teams', 0, false)]),
      away: team('CAR', [f('third_down', -3.8, true), f('kicking', 1.7, false), f('special_teams', 0, false)]),
    },
  } as unknown as RetroGame

  it('nets the two teams on one bar, so one side\'s miss reads as the other\'s gain', () => {
    const { variance, pure, net } = swingRows(r)
    expect(variance.map((x) => [x.key, x.value])).toEqual([['third_down', 11.9]])
    expect(pure.map((x) => [x.key, x.value])).toEqual([['kicking', -2.5]])
    expect(net).toBe(9.4)
  })
  it('keeps what each team did, and leaves out a factor nobody moved', () => {
    const { pure } = swingRows(r)
    expect(pure[0].teams.map((t) => [t.team, t.swing])).toEqual([['CAR', 1.7], ['GB', -0.8]])
    expect(pure.map((x) => x.key)).not.toContain('special_teams')
  })
})

describe('playedLikeSteps', () => {
  const r = (over: object) => ({ home: 'GB', away: 'CAR', played_like: { p_home: 0.4, home_epa: 0.01, away_epa: 0.06, home_success: 0.45, away_success: 0.5, p_base: 0.59, ...over } }) as unknown as RetroGame
  it('names the team with the edge, even when that moves the home side down', () => {
    expect(playedLikeSteps(r({}))?.sentence).toBe("Before any plays, the home side wins 59% of the time. CAR's edge of 0.050 EPA a play moves GB to 40%.")
  })
  it('is null on a record without the inputs', () => {
    expect(playedLikeSteps(r({ p_base: null }))).toBeNull()
  })
})

describe('phaseSummary', () => {
  const r = (...leaders: ('home' | 'away' | null)[]) => ({ home: 'GB', away: 'CAR', phases: leaders.map((leader) => ({ leader })) }) as unknown as RetroGame
  it('counts every phase, even ones nobody won', () => {
    expect(phaseSummary(r('home', 'home', 'away', null))).toBe('GB won 2 of 4 phases')
    expect(phaseSummary(r('away', 'away', 'away'))).toBe('CAR won 3 of 3 phases')
  })
  it('says when the teams split them', () => {
    expect(phaseSummary(r('home', 'away', null))).toBe('CAR and GB split the phases 1–1')
  })
})

describe('edges that are not edges', () => {
  it('keeps the bar but not the label on a venue row, and on a neutral site a rest row too', () => {
    const pp = (v: number) => ({ pp: v, features: {} })
    const g = {
      ...game, neutral_site: true,
      edges: { venue_weather: { favors: 'CAR', strength_pct: 98 }, rest_travel: { favors: 'CAR', strength_pct: 93 }, quality: { favors: 'GB', strength_pct: 90 } },
      contributions: { global: { p_home: 0.5, home_field_pp: 0, groups: { venue_weather: pp(-4), rest_travel: pp(-1), quality: pp(7) } } },
    } as unknown as Game
    const rows = Object.fromEntries(previewRows(g, meta, null).map((r) => [r.id, r]))
    expect(rows.venue_weather).toMatchObject({ edge: '', pct: null, pp: -4 })
    expect(rows.rest_travel).toMatchObject({ edge: '', pct: null, pp: -1 })
    expect(rows.quality.edge).toBe('GB, 90th pct')
    expect(previewRows({ ...g, neutral_site: false }, meta, null).find((r) => r.id === 'rest_travel')?.edge).toBe('CAR, 93rd pct')
  })
  it('leaves them out of the edge list', () => {
    const edges = { venue_weather: { favors: 'CAR', strength_pct: 98 }, rest_travel: { favors: 'CAR', strength_pct: 93 }, quality: { favors: 'GB', strength_pct: 100 } }
    expect(edgeRows(edges, meta, true).rows.map((r) => r.id)).toEqual(['quality'])
    expect(edgeRows(edges, meta).rows.map((r) => r.id)).toEqual(['quality', 'rest_travel'])
    expect(edgeRows(edges, meta).rows[0].sentence).toContain('99th percentile')
  })
})

describe('home field on a neutral site', () => {
  const venue = (pp: number, n: number) => ({ pp, features: { 'environment.neutral_site': n, 'environment.is_turf': pp - n } })
  const c = (hf: number, pp: number, n: number) => ({ p_home: 0.5, home_field_pp: hf, groups: { venue_weather: venue(pp, n) } })
  const g = (neutral: boolean) => ({ ...game, neutral_site: neutral, edges: {}, contributions: { global: c(6, -3.2, -3.8), student: c(6.3, -4, -4.6) } }) as unknown as Game

  it('moves the neutral-site discount from Venue & weather onto the home field row', () => {
    const rows = Object.fromEntries(previewRows(g(true), meta, 'student').map((r) => [r.id, r]))
    expect(rows.home_field.pp).toBeCloseTo(2.2)
    expect(rows.home_field.overlay).toBeCloseTo(1.7)
    expect(rows.venue_weather.pp).toBeCloseTo(0.6)
    expect(rows.venue_weather.overlay).toBeCloseTo(0.6)
    expect(rows.home_field.edge).toBe('neutral site')
  })
  it('leaves a home game alone', () => {
    const rows = Object.fromEntries(previewRows(g(false), meta, 'student').map((r) => [r.id, r]))
    expect(rows.home_field).toMatchObject({ pp: 6, overlay: 6.3 })
    expect(rows.venue_weather.pp).toBeCloseTo(-3.2)
  })
})

