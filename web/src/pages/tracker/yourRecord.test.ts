import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { CustomSeason, type CustomGame } from '../../data/contract'
import { scoreLine } from '../../you/line'
import { yourRecord } from './yourRecord'
import { summaryTiles } from './summary'
import { Tracker } from '../../data/contract'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const season = CustomSeason.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'custom_2026.json'), 'utf8')))
const line = { W: { quality: 0.5, offense: 0.5 }, intercept: 0, a: 1, c: 0.1 }
const you = { line, savedAt: '2026-10-20T00:00:00Z' }

describe('yourRecord', () => {
  const rec = yourRecord(season, you)
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length

  it('counts every game and picks right for the three lines', () => {
    expect(rec.all.you.n).toBe(season.games.length)
    const right = (p: (g: CustomGame) => number | null) =>
      season.games.filter((g) => { const x = p(g); return x != null && x !== 0.5 && (x > 0.5) === (g.home_won === 1) }).length
    expect(rec.all.you.right).toBe(right((g) => scoreLine(line, g).p_home))
    expect(rec.all.student.right).toBe(right((g) => g.p_student))
    expect(rec.all.market.right).toBe(right((g) => g.p_market))
  })

  it('mean log loss matches a hand computation', () => {
    const ll = (p: number, w: number) => -Math.log(w === 1 ? p : 1 - p)
    expect(rec.all.you.logLoss).toBeCloseTo(mean(season.games.map((g) => ll(scoreLine(line, g).p_home, g.home_won))), 10)
    expect(rec.all.market.logLoss).toBeCloseTo(mean(season.games.map((g) => ll(g.p_market!, g.home_won))), 10)
  })

  it('cumulative log loss by week ends at the season mean', () => {
    expect(rec.weeks.map((w) => w.week)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
    expect(rec.weeks.at(-1)!.you).toBeCloseTo(rec.all.you.logLoss!, 10)
  })

  it('since saved counts only games that kicked off after the save', () => {
    const after = season.games.filter((g) => Date.parse(g.kickoff_utc!) > Date.parse(you.savedAt))
    expect(after.length).toBeGreaterThan(0)
    expect(after.length).toBeLessThan(season.games.length)
    expect(rec.since.you.n).toBe(after.length)
    expect(yourRecord(season, { line, savedAt: '2030-01-01T00:00:00Z' }).since.you.n).toBe(0)
  })

  it('a null probability skips that line only; exactly 0.5 counts for nobody', () => {
    const games = season.games.slice(0, 4).map((g, i) => ({ ...g, p_market: i === 0 ? null : 0.5 }))
    const r = yourRecord({ ...season, games }, you)
    expect(r.all.market.n).toBe(3)
    expect(r.all.market.right).toBe(0)
    expect(r.all.you.n).toBe(4)
  })
})

describe('tracker summary with the headline "you"', () => {
  const t = Tracker.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'tracker.json'), 'utf8')))
  it('swaps only the first tile for the unofficial record', () => {
    const tiles = summaryTiles(t, 'you', yourRecord(season, you))
    expect(tiles[0]).toMatchObject({ id: 'season', label: 'Your line vs the market', tab: 'you', modelId: 'you' })
    expect(tiles[0].sub).toBe(`unofficial · ${season.games.length} games`)
    expect(tiles.slice(1)).toEqual(summaryTiles(t).slice(1))
  })
  it('shows a dash before the record is ready', () => {
    expect(summaryTiles(t, 'you', null)[0]).toMatchObject({ value: '–', tab: 'you' })
  })
})
