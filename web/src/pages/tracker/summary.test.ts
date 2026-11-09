import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { Tracker } from '../../data/contract'
import { summaryTiles } from './summary'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const t = Tracker.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'tracker.json'), 'utf8')))

describe('tracker summaryTiles', () => {
  it('builds the five tiles, each pointing at a tab', () => {
    const tiles = summaryTiles(t)
    expect(tiles.map((x) => x.id)).toEqual(['season', 'live', 'best', 'calibration', 'bets'])
    expect(tiles.map((x) => x.tab)).toEqual(['season', 'season', 'season', 'calibration', 'bets'])
    expect(tiles.every((x) => x.value.length <= 20)).toBe(true)
  })

  it('says "about the same" inside the noise band and ranks outside it', () => {
    const rows = (p: number) => [
      ...[1, 2].map((week) => ({ model_id: 'market_baseline', week, n: 8, cum_log_loss: 0.6, live: false })),
      ...[1, 2].map((week) => ({ model_id: 'student', week, n: 8, cum_log_loss: p, live: false })),
    ]
    const tile = (p: number) => summaryTiles({ ...t, current_season: rows(p) })[0]
    expect(tile(0.62)).toMatchObject({ value: 'Same as market', sub: 'within 0.025 over 16 games' })
    expect(tile(0.64)).toMatchObject({ value: 'Trails the market', sub: '0.040 behind, 16 games' })
    expect(tile(0.56)).toMatchObject({ value: 'Beats the market' })
  })

  it('best approach: names a leader outside the band, "too close to call" inside it', () => {
    const rows = (lls: Record<string, number>) => [
      { model_id: 'market_baseline', week: 1, n: 8, cum_log_loss: 0.6, live: false },
      ...Object.entries(lls).map(([model_id, cum_log_loss]) => ({ model_id, week: 1, n: 8, cum_log_loss, live: false })),
    ]
    const best = (lls: Record<string, number>) => summaryTiles({ ...t, current_season: rows(lls) })[2]
    const close = best({ student: 0.61, analyst: 0.62 })
    expect(close).toMatchObject({ value: 'Too close to call', sub: 'Student lowest, within noise' })
    expect(close.modelId).toBeUndefined()
    const clear = best({ student: 0.61, analyst: 0.65 })
    expect(clear.value).not.toBe('Too close to call')
    expect(clear.modelId).toBe('student')
    expect(clear.sub).toBe('0.610, about the same as the market')
    expect(best({ student: 0.61 }).modelId).toBe('student')
  })

  it('counts live games only from live rows; none means all backfill', () => {
    expect(summaryTiles({ ...t, current_season: t.current_season.map((r) => ({ ...r, live: false })) })[1]).toMatchObject({ value: 'None yet' })
    const live = t.current_season.map((r) => ({ ...r, live: r.week <= 2 }))
    expect(summaryTiles({ ...t, current_season: live })[1]).toMatchObject({ value: expect.stringMatching(/^\d+$/), sub: 'over 2 weeks; the rest is backfill' })
  })

  it('bets: prefers the live Student row, signs the units, falls back to backfill', () => {
    const base = { model_id: 'student', bets: 10, wins: 6, losses: 4, pushes: 0, roi: 0.1, clv: null }
    const live = summaryTiles({ ...t, ledger: [{ ...base, kind: 'backfill', units: -126, bets: 3603 }, { ...base, kind: 'live', units: 3.24 }] })[4]
    expect(live).toMatchObject({ value: '+3.2 units', sub: '6-4 on 10 live bets' })
    // the backfill spans every season since 2005, so it is told per bet
    const back = summaryTiles({ ...t, ledger: [{ ...base, kind: 'backfill', units: -126.04, roi: -0.035, bets: 3648 }], ledger_seasons: [{ model_id: 'student', season: 2006 }, { model_id: 'student', season: 2007 }] as never })[4]
    expect(back).toMatchObject({ label: 'Paper bets, backtest', value: '−3.5% a bet' })
    expect(back.sub).toBe('Student: 3,648 bets since 2006')
    expect(summaryTiles({ ...t, ledger: [] })[4].value).toBe('None yet')
  })

  it('calibration: a verdict, not a number', () => {
    expect(summaryTiles(t)[3].value).toMatch(/Well calibrated|Overconfident|Underconfident|Too few to judge/)
    expect(summaryTiles(t)[3].sub).toMatch(/^60–80% calls won \d+%$/)
    expect(summaryTiles({ ...t, reliability: [] })[3].value).toBe('Too few to judge')
  })
})
