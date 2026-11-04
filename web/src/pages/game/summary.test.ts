import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { Game, Meta, RetroGame } from '../../data/contract'
import { summaryTiles } from './summary'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const load = (p: string) => JSON.parse(fs.readFileSync(path.join(FIX, p), 'utf8'))
const meta = Meta.parse(load('meta.json'))
const game = Game.parse(load('game/2026_08_CAR_GB.json'))
const retro = RetroGame.parse(load('retro/2026_08_CAR_GB.json'))
const final = { ...game, result: { home_score: 20, away_score: 23, margin: -3 } }

describe('summaryTiles', () => {
  it('pregame: the pick, vs the market, the split, the biggest factor, and an edge when no one is out', () => {
    const t = summaryTiles(game, meta, null)
    expect(t.map((x) => x.id)).toEqual(['pick', 'market', 'split', 'factor', 'edge'])
    expect(t.every((x) => x.tab === 'forecast')).toBe(true)
    expect(t[0]).toMatchObject({ value: expect.stringMatching(/^GB \d+%$/), modelId: 'ensemble' })
    // every approach leans further toward GB than the market (divergence +5 to +8 pts)
    expect(t[1].value).toMatch(/pts more on GB|In line/)
    expect(t[2]).toMatchObject({ value: 'All on GB', sub: '4 of 4 agree' })
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
    expect(abs).toMatchObject({ value: 'Q Starter', sub: 'CAR QB, out · +1 more', tab: 'news' })
  })

  it('pregame: ranks absences by position and skips long-term lists', () => {
    const inj = (player: string, pos: string, status: string) => ({ week: 8, team: 'GB', player, pos, status, practice: null, injury: null })
    const g = { ...game, injuries: [inj('A Linebacker', 'LB', 'Out'), inj('B Receiver', 'WR', 'Doubtful'), inj('C Tackle', 'T', 'Out'), inj('A Quarterback', 'QB', 'Reserve/Injured (IR)')] }
    // the IR quarterback is not this week's news; a doubtful receiver outranks an out linebacker
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'absence')).toMatchObject({ value: 'B Receiver', sub: 'GB WR, doubtful · +2 more' })
  })

  it('pregame: a 3–1 split names the dissenter', () => {
    const g = structuredClone(game)
    g.models.sharp.p_home = 0.4
    expect(summaryTiles(g, meta, null).find((x) => x.id === 'split')).toMatchObject({ value: '3–1 GB', sub: 'Sharp takes CAR' })
  })

  it('post-game: result, approaches right, played like, swing plays, biggest surprise', () => {
    const t = summaryTiles(final, meta, retro)
    expect(t.map((x) => x.id)).toEqual(['result', 'right', 'played', 'swing', 'surprise'])
    expect(t.every((x) => x.tab === 'retro')).toBe(true)
    expect(t[0]).toMatchObject({ value: 'Upset', sub: expect.stringMatching(/^CAR won as a \d+% underdog$/) })
    expect(t[1]).toMatchObject({ value: '0 of 4', sub: 'best read: Traditionalist', modelId: 'traditionalist' })
    expect(t[2]).toMatchObject({ value: 'GB 61%', sub: 'the better side, but lost' })
    // GB net −9.6, CAR +5.3: the swing plays went to CAR by 14.9
    expect(t[3].value).toBe('CAR +14.9 pts')
    expect(t[4].sub).toMatch(/^(better|worse) than its season by \d\.\d\d EPA a (play|dropback|rush)$/)
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
