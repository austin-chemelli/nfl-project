import { describe, expect, it } from 'vitest'
import metaJson from '../../test/fixtures/site/meta.json'
import retroJson from '../../test/fixtures/site/retro/2026_08_CAR_GB.json'
import gameJson from '../../test/fixtures/site/game/2026_08_CAR_GB.json'
import { Game, Meta, RetroGame } from '../../data/contract'
import { byUnit, contributionItems, dotModels, edgeRows, featureContribRows, impactMarker, injuryRank, lineMoveChip, liveOnlyGroups, ordinal, phaseSummary, playedLikeSteps, previewRows, sortInjuries, sortMatchupNotes, swingRows, tape, tendencyBlocks, marketSource, trendStatus, wpLede, markText, driveText, driveLede, liveReady, liveBars } from './helpers'

const meta = Meta.parse(metaJson)
const game = Game.parse(gameJson)

describe('game helpers', () => {
  it('ordinals', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 78, 88, 100].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '78th', '88th', '100th'])
  })
  it('edge sentences as percentiles, strongest first', () => {
    const { rows } = edgeRows(game.edges, meta)
    expect(rows[0].sentence).toBe(`${rows[0].favors}'s ${rows[0].name} edge is bigger than ${Math.min(99, Math.round(rows[0].pct))}% of matchups`)
    expect(rows[0].sentence).toMatch(/^[A-Z]+'s .+ edge is bigger than \d+% of matchups$/)
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

describe('liveOnlyGroups', () => {
  const withFeatures = (f: Record<string, unknown>) => ({ ...game, features: { ...game.features, ...f } }) as Game
  it('lists the groups the history fit has no bar for, never context-only ones, in registry order', () => {
    expect(liveOnlyGroups(game, meta).map((x) => x.id)).toEqual(['market', 'buzz'])
  })
  it('signs a negative index with a minus, as the rest of the site does', () => {
    const buzz = liveOnlyGroups(withFeatures({ 'narrative.sentiment': { group: 'buzz', away: -0.5, home: 0.2 } }), meta).find((x) => x.id === 'buzz')!
    const s = buzz.readings.find((r) => r.feature === 'narrative.sentiment')!
    expect([s.away, s.home]).toEqual(['−0.50', '0.20'])
  })
  it('reads a line move and a public share toward a side, and team readings per team', () => {
    const [market, buzz] = liveOnlyGroups(withFeatures({
      'market.line_move_pts': { group: 'market', game: -2.5 },
      'narrative.public_bet_pct_home': { group: 'market', game: 0.94 },
    }), meta)
    expect(market.readings.map((r) => r.game)).toEqual([`2.5 pts toward ${game.away}`, `94% on ${game.home}`])
    const hype = buzz.readings.find((r) => r.feature === 'narrative.hype')!
    expect([hype.away, hype.home, hype.game]).toEqual(['0.40', '0.50', null])
  })
  it('keeps a group with no readings, each reading null', () => {
    const none = { ...game, features: {} } as Game
    const market = liveOnlyGroups(none, meta).find((x) => x.id === 'market')!
    expect(market.readings.every((r) => r.game == null && r.away == null && r.home == null)).toBe(true)
  })
  it('is empty without the history fit', () => {
    expect(liveOnlyGroups({ ...game, contributions: {} } as Game, meta)).toEqual([])
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
    expect(edgeRows(edges, meta).rows[0].sentence).toContain('bigger than 99% of matchups')
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

describe('marketSource and trendStatus', () => {
  it('names the market source and snapshot time', () => {
    const at = { p_home: 0.6, as_of: '2026-10-27T22:46:59Z' }
    expect(marketSource({ ...at, source: 'odds_api' })).toBe('Market line: The Odds API, Tue, Oct 27, 6:46 PM ET.')
    // a schedule line's as_of is synthetic, so it never prints as a time
    expect(marketSource({ ...at, source: 'schedules' })).toBe('Market line: the nflverse schedule (no time recorded).')
    expect(marketSource({ ...at, source: 'other' })).toMatch(/^Market line: other, /)
    expect(marketSource({ ...at, source: null })).toBeNull()
    expect(marketSource({ ...at, source: 'odds_api', as_of: null })).toBe('Market line: The Odds API.')
    expect(marketSource({ ...at, source: 'schedules', p_home: null })).toBeNull()
    expect(marketSource(null)).toBeNull()
  })
  it('trend status wording', () => {
    expect([true, false, null].map(trendStatus)).toEqual(['producing results', 'not producing results', 'results unclear'])
  })
})

describe('wpLede and markText', () => {
  const base = RetroGame.parse(JSON.parse(JSON.stringify(retroJson)))
  const with_ = (o: { home: number; away: number; low: [number, number] | null; ot?: boolean; min?: number }) => {
    const r = structuredClone(base)
    r.result = { home_score: o.home, away_score: o.away, margin: o.home - o.away }
    r.home = 'DAL'
    r.away = 'ARI'
    Object.assign(r.wp_series!, { winner_low: o.low, ot: o.ot ?? false, points: [[0, 0.77], [100, o.min ?? 0.6], [3600, o.home > o.away ? 1 : 0]] })
    return r
  }
  it('comeback, with the quarter', () => {
    expect(wpLede(with_({ home: 30, away: 33, low: [1000, 0.04] }))).toBe('ARI won 33–30 after its win chance fell to 4% in Q2.')
    expect(wpLede(with_({ home: 30, away: 33, low: [3700, 0.004], ot: true }))).toBe('ARI won 33–30 after its win chance fell to under 1% in overtime.')
  })
  it('wire to wire', () => {
    // an underdog that only rose never "fell" to where it started
    expect(wpLede(with_({ home: 30, away: 33, low: [0, 0.134] }))).toBe("ARI's win chance never fell below 13% on the way to a 33–30 win.")
    expect(wpLede(with_({ home: 31, away: 20, low: [100, 0.58] }))).toContain('below 58%') // 0.58 * 100 is 57.99...
    expect(wpLede(with_({ home: 31, away: 20, low: [100, 0.589] }))).toBe("DAL's win chance never fell below 58% on the way to a 31–20 win.")
  })
  it('tie, and no series', () => {
    expect(wpLede(with_({ home: 20, away: 20, low: null }))).toBe('Tied 20–20.')
    expect(wpLede(with_({ home: 20, away: 20, low: null, ot: true }))).toBe('Tied 20–20 after overtime.')
    expect(wpLede({ ...base, wp_series: null })).toBeNull()
  })
  it('markText names the team helped, with and without a factor', () => {
    const p = base.wp_series!.plays[0] // GB fumble, wpa -0.425: helps the away side
    const m = markText(p, 'GB', 'CAR', 'Fumble recoveries')
    expect(m).toMatchObject({ title: 'Q4 3:02 · GB', helped: 'away', team: 'CAR', prob: '36% → 79%', swing: '+43 pts', counted: 'Counted in: Fumble recoveries' })
    expect(markText({ ...p, qtr: 5, wpa: 0.1, team: null }, 'GB', 'CAR')).toMatchObject({ title: 'OT 3:02', helped: 'home', team: 'GB', counted: null })
  })
  it('states a swing its own two numbers add up to, and leaves the repeated clock off the play text', () => {
    const p = { play_id: 1, t: 3727, qtr: 5, clock: '7:53', team: 'DAL', p_before: 0.469, p_after: 0.275, wpa: -0.194, factor: null, text: '(7:53) (Shotgun) D.Prescott sacked' }
    expect(markText(p, 'DAL', 'ARI')).toMatchObject({ prob: '53% → 73%', swing: '+20 pts', text: '(Shotgun) D.Prescott sacked' })
    expect(markText({ ...p, text: '(:10) pass' }, 'DAL', 'ARI').text).toBe('pass')
    expect(markText({ ...p, text: 'Kickoff (3:02) note' }, 'DAL', 'ARI').text).toBe('Kickoff (3:02) note')
  })
})

describe('driveText and driveLede', () => {
  const dr = { n: 1, team: 'ARI', qtr: 2, t0: 1000, t1: 1190, start_yl: 31, end_yl: 62, plays: 7, result: 'Punt' }
  it('says when, how it ended, and where it went from the offense\'s view', () => {
    expect(driveText(dr)).toEqual({ title: 'Q2 · ARI', result: 'Punt', span: '7 plays, 3:10', detail: "From own 31 to opponent's 38" })
  })
  it('takes a touchdown to the end zone, and handles overtime, midfield and missing fields', () => {
    expect(driveText({ ...dr, qtr: 5, result: 'Touchdown', start_yl: 50 })).toMatchObject({ title: 'OT · ARI', detail: 'From midfield to the end zone' })
    expect(driveText({ ...dr, plays: 1 }).span).toBe('1 play, 3:10')
    expect(driveText({ ...dr, plays: null, start_yl: null, end_yl: null, result: null })).toMatchObject({ result: 'Result not recorded', span: '3:10', detail: null })
    expect(driveText({ ...dr, end_yl: null }).detail).toBe('From own 31')
    expect(driveText({ ...dr, result: 'Opp touchdown' }).result).toBe('Touchdown for the defense')
  })
  it('counts each team\'s scoring drives, away first', () => {
    const r = { away: 'ARI', home: 'DAL', drives: [dr, { ...dr, result: 'Touchdown' }, { ...dr, team: 'DAL', result: 'Field goal' }] } as unknown as RetroGame
    expect(driveLede(r)).toBe('ARI scored on 1 of 2 drives, DAL on 1 of 1.')
    expect(driveLede({ ...r, drives: null })).toBeNull()
  })
})

describe('liveReady', () => {
  const grp = (readings: { feature: string; game?: string | null; away?: string | null; home?: string | null }[]) => ({
    id: 'g', name: 'G', help: '', readings: readings.map((r) => ({ label: r.feature, help: '', game: null, away: null, home: null, ...r })),
  })
  it('waits for the narrative pass: a line-move reading alone is not enough', () => {
    expect(liveReady([grp([{ feature: 'market.line_move_pts', game: 'no move' }, { feature: 'narrative.public_bet_pct_home' }])])).toBe(false)
    expect(liveReady([grp([{ feature: 'narrative.sentiment', away: '0.2' }])])).toBe(true)
  })
})

describe('liveBars', () => {
  const g = Game.parse(gameJson)
  const meta = Meta.parse(metaJson)
  it('puts each live reading on its own scale, toward its side, in its own units', () => {
    const bars = liveBars(g, meta)
    const by = Object.fromEntries(bars.map((b) => [b.feature, b]))
    expect(by['market.line_move_pts']).toMatchObject({ text: '0.0 pts', lean: 0, toward: null })
    expect(by['narrative.public_bet_pct_home'].text).toBe('51% on GB')
    for (const b of bars) if (b.lean != null) expect(Math.abs(b.lean)).toBeLessThanOrEqual(1)
  })
  it('a public-betting share under half reads on the away side', () => {
    const away = { ...g, features: { ...g.features, 'narrative.public_bet_pct_home': { group: 'market', game: 0.35 } } } as typeof g
    const b = liveBars(away, meta).find((x) => x.feature === 'narrative.public_bet_pct_home')
    expect(b).toMatchObject({ text: `65% on ${g.away}`, toward: g.away })
    expect(b!.lean).toBeLessThan(0)
  })
})
