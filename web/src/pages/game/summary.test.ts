import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { Game, Meta, RetroGame } from '../../data/contract'
import { pureLuck, summaryTiles } from './summary'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const load = (p: string) => JSON.parse(fs.readFileSync(path.join(FIX, p), 'utf8'))
const meta = Meta.parse(load('meta.json'))
const game = Game.parse(load('game/2026_08_CAR_GB.json'))
const retro = RetroGame.parse(load('retro/2026_08_CAR_GB.json'))
const final = { ...game, result: { home_score: 20, away_score: 23, margin: -3 } }

describe('summaryTiles', () => {
  it('pregame: the pick, vs the market, the biggest factor, and an edge when no one is out', () => {
    const t = summaryTiles(game, meta, null)
    expect(t.map((x) => x.id)).toEqual(['pick', 'market', 'factor', 'edge'])
    expect(t.map((x) => x.tab)).toEqual(['approaches', 'approaches', 'preview', 'preview'])
    expect(t[0]).toMatchObject({ value: expect.stringMatching(/^GB \d+%$/), sub: expect.stringMatching(/^the Student's line, (GB|CAR) −[\d.]+$|^the Student's line, pick'em$/), modelId: 'student' })
    // every approach leans further toward GB than the market (divergence +5 to +8 pts)
    expect(t[1].value).toMatch(/pts more on GB|In line/)
  })

  it('pregame: a locked total adds the expected score, favorite first', () => {
    const g = { ...game, expected_score: { total: 44.6, sd: 13.4, market_total: 41.5, lock_ts: null, home: 24.4, away: 20.2 } }
    const t = summaryTiles(g, meta, null)
    expect(t.map((x) => x.id)).toEqual(['pick', 'market', 'factor', 'edge', 'score'])
    expect(t[4]).toMatchObject({ label: 'Expected score', value: 'GB 24–20 CAR', sub: 'total 44.6, market 41.5', team: 'GB' })
    const noSpread = { ...g, expected_score: { ...g.expected_score, home: null, away: null, market_total: null } }
    expect(summaryTiles(noSpread, meta, null)[4]).toMatchObject({ value: 'Total 45', sub: 'total 44.6, no market total' })
  })

  it('pregame: the factor tile names the Student and says pts of win chance', () => {
    const f = summaryTiles(game, meta, null).find((x) => x.id === 'factor')
    expect(f?.sub).toMatch(/^\d+\.\d win-chance pts toward (GB|CAR), Student$/)
  })

  it('pregame: at a neutral site the home field tile carries the neutral discount, as the Preview chart does', () => {
    const c = game.contributions.student!
    const contributions = { ...game.contributions, student: { ...c, home_field_pp: 7.1, groups: { venue_weather: { pp: -4.1, features: { 'environment.neutral_site': -4.1 } } } } }
    const f = summaryTiles({ ...game, neutral_site: true, contributions }, meta, null).find((x) => x.id === 'factor')
    expect(f).toMatchObject({ value: 'Home field' })
    expect(f?.sub).toMatch(/^3\.0 win-chance pts toward \w+ \(7\.1, less 4\.1 for a neutral site\), Student$/)
  })

  it('pregame: the biggest edge is never a context-only group', () => {
    const g = { ...game, edges: { coaching: { favors: 'GB', strength_pct: 99 }, quality: { favors: 'CAR', strength_pct: 60 } } }
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'edge')).toMatchObject({ value: 'CAR Quality' })
  })

  it('pregame: the biggest edge is never Venue & weather, which only moves home advantage', () => {
    const g = { ...game, edges: { venue_weather: { favors: 'CAR', strength_pct: 98 }, quality: { favors: 'GB', strength_pct: 60 } } }
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'edge')).toMatchObject({ value: 'GB Quality' })
  })

  it('pregame: on a neutral site Rest & travel is not an edge either, and no edge says 100%', () => {
    const edges = { rest_travel: { favors: 'CAR', strength_pct: 93 }, quality: { favors: 'GB', strength_pct: 99.7 } }
    expect(summaryTiles({ ...game, neutral_site: true, edges: { ...edges, quality: { favors: 'GB', strength_pct: 60 } } }, meta, null).find((x) => x.id === 'edge')).toMatchObject({ value: 'GB Quality' })
    expect(summaryTiles({ ...game, edges }, meta, null).find((x) => x.id === 'edge')).toMatchObject({ sub: 'bigger than 99% of matchups' })
  })

  it('pregame: dates a market line more than 3 days old', () => {
    const g = { ...game, market: { ...game.market!, as_of: '2026-10-20T15:00:00Z' } }
    const m = { ...meta, generated_at: '2026-11-03T20:00:00Z' }
    expect(summaryTiles(g, m, null).find((x) => x.id === 'market')?.sub).toMatch(/ · line from Oct 20$/)
    const fresh = { ...game, market: { ...game.market!, as_of: '2026-11-02T15:00:00Z' } }
    expect(summaryTiles(fresh, m, null).find((x) => x.id === 'market')?.sub).not.toMatch(/line from/)
  })

  it('pregame: names the key absence when someone is out', () => {
    const g = { ...game, injuries: [
      { week: 8, team: 'GB', player: 'A Backup', pos: 'WR', status: 'Doubtful', practice: null, injury: null },
      { week: 8, team: 'CAR', player: 'Q Starter', pos: 'QB', status: 'Out', practice: null, injury: null },
    ] }
    const abs = summaryTiles(g, meta, null).find((x) => x.id === 'absence')
    expect(abs).toMatchObject({ value: 'Q Starter', sub: 'CAR QB, out · +1 more', tab: 'health' })
  })

  it('pregame: ranks absences by position and skips long-term lists', () => {
    const inj = (player: string, pos: string, status: string) => ({ week: 8, team: 'GB', player, pos, status, practice: null, injury: null })
    const g = { ...game, injuries: [inj('A Linebacker', 'LB', 'Out'), inj('B Receiver', 'WR', 'Doubtful'), inj('C Tackle', 'T', 'Out'), inj('A Quarterback', 'QB', 'Reserve/Injured (IR)')] }
    // the IR quarterback is not this week's news; a doubtful receiver outranks an out linebacker
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'absence')).toMatchObject({ value: 'B Receiver', sub: 'GB WR, doubtful · +2 more' })
  })

  it('post-game: the game first and the approaches last', () => {
    const t = summaryTiles(final, meta, retro)
    expect(t.map((x) => x.id)).toEqual(['result', 'played', 'swing', 'surprise', 'right'])
    expect(t.every((x) => x.tab === 'retro')).toBe(true)
    expect(t[0]).toMatchObject({ value: 'Upset', sub: expect.stringMatching(/^CAR won as a \d+% underdog (before kickoff|at lock)$/) })
    expect(t[1]).toMatchObject({ label: 'Deserved to win', value: 'GB 79%', sub: 'GB by 3.4 on the plays, but lost', team: 'GB' })
    // GB net −9.6, CAR +5.3: the swing plays went to CAR by 14.9 net; underneath, each team's own pure luck
    expect(t[2].value).toBe('CAR +14.9 pts net')
    // each team's own pure luck, signed like the headline sentence and the recap, not the gap between them
    const signed = (x: number) => `${x < 0 ? '−' : '+'}${Math.abs(x).toFixed(1)}`
    expect(t[2].sub).toBe(`pure luck CAR ${signed(pureLuck(retro.teams.away))}, GB ${signed(pureLuck(retro.teams.home))}`)
    expect(t[3].sub).toMatch(/^(better|worse) than its season by \d\.\d\d EPA a (play|dropback|rush)$/)
    expect(t[4]).toMatchObject({ value: '0 of 4', sub: 'best read: Traditionalist', modelId: 'traditionalist' })
  })

  it('post-game: the played-like tile on a retro from before schema 8, and a toss-up meter', () => {
    expect(summaryTiles(final, meta, { ...retro, deserved: undefined })[1]).toMatchObject({ label: 'Played like', value: 'GB 61%', sub: 'the better side, but lost' })
    const close = { ...retro, deserved: { ...retro.deserved!, p_home: 0.55, margin_home: 0.6 } }
    expect(summaryTiles(final, meta, close)[1]).toMatchObject({ value: 'Toss-up', team: undefined, sub: 'GB by 0.6 on the plays, but lost' })
  })

  it('post-game: a tie has no "right" count', () => {
    const tie = { ...game, result: { home_score: 20, away_score: 20, margin: 0 } }
    expect(summaryTiles(tie, meta, retro).find((x) => x.id === 'right')).toMatchObject({ value: '–', sub: 'a tie · best read: Traditionalist' })
    expect(summaryTiles(tie, meta, null).find((x) => x.id === 'right')).toMatchObject({ value: '–', sub: 'a tie' })
    expect(summaryTiles(tie, meta, retro)[0].value).toBe('Tie')
  })

  it('post-game without a retro yet: what the game file can say', () => {
    const t = summaryTiles(final, meta, null)
    expect(t.map((x) => x.id)).toEqual(['result', 'right', 'pick', 'factor', 'pending'])
    expect(t[1]).toMatchObject({ value: '0 of 4', sub: 'none picked the winner' })
  })
})

describe('summaryTiles with the reader\'s own line as the headline', () => {
  const you = { ...game.models.student, p_home: 0.4, spread_home: 1.5, status: 'preview' as const }
  const g = { ...game, models: { ...game.models, you }, contributions: { ...game.contributions, you: game.contributions.student } }
  it('leads with your line, unofficial, and keeps its colour', () => {
    const pick = summaryTiles(g, meta, null, 'you').find((x) => x.id === 'pick')
    expect(pick).toMatchObject({ modelId: 'you', value: 'CAR 60%' })
    expect(pick?.sub).toMatch(/^your line \(unofficial\), /)
  })
  it('names your line in the factor tile and leaves the default alone', () => {
    expect(summaryTiles(g, meta, null, 'you').find((x) => x.id === 'factor')?.sub).toMatch(/, your line$/)
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'pick')).toMatchObject({ modelId: 'student' })
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'factor')?.sub).toMatch(/, Student$/)
  })
  it('counts only the published approaches as right, never the reader\'s own line', () => {
    const f = { ...g, models: { ...g.models, analyst: { ...you } }, result: { home_score: 20, away_score: 23, margin: -3 } }
    const sub = summaryTiles(f, meta, null).find((x) => x.id === 'right')?.sub ?? ''
    expect(sub).not.toMatch(/You/)
  })
})
