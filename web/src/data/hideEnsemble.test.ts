import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import * as C from './contract'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site')
const load = (rel: string) => JSON.parse(fs.readFileSync(path.join(FIX, rel), 'utf8'))
const ids = (rows: { model_id: string }[]) => rows.map((r) => r.model_id)

describe('the ensemble never reaches a page', () => {
  it('leaves the slate and the game file, with or without it in the data', () => {
    const raw = load('game/2026_08_CAR_GB.json')
    expect(raw.models).toHaveProperty('ensemble')
    const g = C.Game.parse(raw)
    expect(g.models).not.toHaveProperty('ensemble')
    expect(g.contributions).not.toHaveProperty('ensemble')
    expect(g.models).toHaveProperty('student')

    delete raw.models.ensemble
    delete raw.contributions.ensemble
    expect(C.Game.parse(raw)).toEqual(g)

    for (const row of C.Slate.parse(load('slate_2026_08.json')).games) expect(row.models).not.toHaveProperty('ensemble')
  })

  it('leaves every tracker list', () => {
    const t = C.Tracker.parse(load('tracker.json'))
    for (const rows of [t.seasons, t.current_season, t.backtest, t.reliability, t.divergence, t.ledger]) {
      expect(ids(rows)).not.toContain('ensemble')
      expect(ids(rows)).toContain('student')
    }
  })

  it('retro: the best approach takes the flag when the ensemble was best, and the headline naming it goes', () => {
    const raw = load('retro/2026_08_CAR_GB.json')
    const ens = raw.predictions.find((p: { model_id: string }) => p.model_id === 'ensemble')
    for (const p of raw.predictions) p.best = p === ens
    ens.log_loss = 0.01
    raw.best_model = 'ensemble'
    raw.headlines = [...raw.headlines, 'Ensemble came closest (0.69 log loss); its Offense group helped most.']
    const r = C.RetroGame.parse(raw)
    const approaches = r.predictions.filter((p) => p.kind === 'approach')
    const lowest = approaches.reduce((a, p) => (p.log_loss < a.log_loss ? p : a))
    expect(ids(r.predictions)).not.toContain('ensemble')
    expect(ids(r.attribution)).not.toContain('ensemble')
    expect(r.best_model).toBe(lowest.model_id)
    expect(r.predictions.filter((p) => p.best).map((p) => p.model_id)).toEqual([lowest.model_id])
    expect(r.headlines.join(' ')).not.toMatch(/ensemble/i)
  })

  it('retro: an approach that was already best keeps the flag', () => {
    const raw = load('retro/2026_08_CAR_GB.json')
    expect(C.RetroGame.parse(raw).best_model).toBe(raw.best_model)
  })

  it('recap: ranks close up, a best ensemble hands over, misread rows built on it go', () => {
    const raw = load('recap_2026_08.json')
    const before = raw.models.filter((m: { model_id: string; rank: number }) => m.rank > 0 && m.model_id !== 'ensemble')
    const ens = raw.models.find((m: { model_id: string }) => m.model_id === 'ensemble')
    for (const m of raw.models) if (m.rank > 0 && m.rank < ens.rank) m.rank += 1
    ens.rank = 1
    raw.best_model = 'ensemble'
    const r = C.WeekRecap.parse(raw)
    expect(ids(r.models)).not.toContain('ensemble')
    expect(r.models.filter((m) => m.rank > 0).map((m) => m.rank).sort()).toEqual(before.map((_: unknown, i: number) => i + 1))
    expect(r.models.find((m) => m.rank === 1)?.model_id).toBe(r.best_model)
    expect(r.misread).toEqual([])
    raw.misread = [{ game_id: 'g', away: 'A', home: 'H', value: 1, sentence: 'The Student gave H 72% and A won 33-30.' }]
    expect(C.WeekRecap.parse(raw).misread).toHaveLength(1)
  })
})
