/**
 * Parity with Python: the TypeScript evaluator against fixtures written by
 * `uv run python scripts/web_fixtures.py --diy` (nfl.approaches.diy on the same small matrix).
 * Deterministic outputs match to 1e-6; the bootstrap intervals use a different random stream, so
 * they are only checked for sanity.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { capMarket, decodeWeights, encodeWeights, evaluate, fitToward, GROUP_IDS, seasonPredictions, type MatrixInput } from './index'

const DIR = path.resolve(import.meta.dirname, '../test/fixtures/diy')
const matrix = JSON.parse(fs.readFileSync(path.join(DIR, 'matrix.json'), 'utf8')) as MatrixInput
const fx = JSON.parse(fs.readFileSync(path.join(DIR, 'parity.json'), 'utf8')) as any

const close = (a: number | null, b: number | null, tol = 1e-6) => {
  if (b == null) return expect(a).toBeNull()
  expect(a).not.toBeNull()
  expect(Math.abs((a as number) - b)).toBeLessThan(tol)
}

function sameSeason(a: any, b: any) {
  expect(a.season).toBe(b.season)
  expect(a.n).toBe(b.n)
  close(a.log_loss, b.log_loss)
  close(a.market_log_loss, b.market_log_loss)
  close(a.delta, b.delta)
  close(a.calib_a, b.calib_a)
  close(a.calib_c, b.calib_c)
  expect(a.in_sample_calibration).toBe(b.in_sample_calibration)
}

describe('group order', () => {
  it('matches the matrix', () => {
    expect([...GROUP_IDS]).toEqual(fx.group_ids)
    expect(matrix.groups).toEqual(fx.group_ids)
  })
})

describe('encode / decode / cap parity', () => {
  it('decodes the same as Python', () => {
    for (const d of fx.decode) {
      const got = decodeWeights(d.s)
      expect(Object.keys(got).sort()).toEqual(Object.keys(d.out).sort())
      for (const [g, v] of Object.entries(d.out)) expect((got[g] as number) + 0).toBe((v as number) + 0)
    }
  })
  it('caps the market group like Python', () => {
    for (const c of fx.cap_market) {
      const [out, hit] = capMarket(c.signed)
      expect(hit).toBe(c.out[1])
      for (const [g, v] of Object.entries(c.out[0])) close(out[g], v as number, 1e-9)
    }
  })
})

describe.each<[string, any]>(fx.cases.map((c: any) => [c.name, c]))('%s', (_name: string, c: any) => {
  const ev = evaluate(c.weights, matrix, { maxSeason: c.max_season })

  it('encodes the share string byte for byte', () => {
    if (c.encoded != null) expect(encodeWeights(c.signed)).toBe(c.encoded)
  })

  it('overall metrics and per-season calibration', () => {
    const e = c.evaluate
    expect(ev.scored_seasons).toEqual(e.scored_seasons)
    expect(ev.overall.n).toBe(e.overall.n)
    expect(ev.overall.seasons).toBe(e.overall.seasons)
    close(ev.overall.log_loss, e.overall.log_loss)
    close(ev.overall.market_log_loss, e.overall.market_log_loss)
    close(ev.overall.delta, e.overall.delta)
    expect(ev.first_season_in_sample).toBe(e.first_season_in_sample)
    expect(ev.seasons).toHaveLength(e.seasons.length)
    ev.seasons.forEach((s, i) => sameSeason(s, e.seasons[i]))
  })

  it('bootstrap intervals contain the estimate and have a sane width', () => {
    const o = ev.overall
    expect(o.ll_lo).toBeLessThanOrEqual(o.log_loss as number)
    expect(o.ll_hi).toBeGreaterThanOrEqual(o.log_loss as number)
    expect(o.ll_hi - o.ll_lo).toBeLessThan(0.1)
    expect(o.d_lo).toBeLessThanOrEqual(o.delta as number)
    expect(o.d_hi).toBeGreaterThanOrEqual(o.delta as number)
    expect(o.d_hi - o.d_lo).toBeLessThan(0.1)
  })

  it('best and worst seasons and their key games', () => {
    for (const k of ['best', 'worst'] as const) {
      expect(ev[k].map((s) => s.season)).toEqual(c.evaluate[k].map((s: any) => s.season))
      ev[k].forEach((s, i) => {
        const want = c.evaluate[k][i].key_games
        expect(s.key_games).toHaveLength(want.length)
        s.key_games?.forEach((g, j) => {
          expect(g.game_id).toBe(want[j].game_id)
          expect(g.group).toBe(want[j].group)
          expect(g.home_won).toBe(want[j].home_won)
          close(g.p, want[j].p)
          close(g.market_p, want[j].market_p)
          close(g.delta, want[j].delta)
          close(g.group_logit, want[j].group_logit)
        })
      })
    }
  })

  it('aging slope', () => {
    close(ev.aging.slope, c.evaluate.aging.slope)
    expect(ev.aging.sentence.startsWith('Too few')).toBe(c.evaluate.aging.slope === null)
  })

  it('context buckets: counts exact, losses close', () => {
    const want = c.evaluate.by_context
    expect(ev.by_context.map((b) => [b.group, b.bucket, b.n])).toEqual(want.map((b: any) => [b.group, b.bucket, b.n]))
    ev.by_context.forEach((b, i) => {
      close(b.log_loss, want[i].log_loss)
      close(b.market_log_loss, want[i].market_log_loss)
      close(b.delta, want[i].delta)
      close(b.delta_se, want[i].delta_se)
    })
  })

  it('divergence buckets and paper bets', () => {
    const want = c.evaluate.divergence
    ev.divergence.forEach((d, i) => {
      expect(d.bucket).toBe(want[i].bucket)
      expect(d.n).toBe(want[i].n)
      close(d.lean_win_rate, want[i].lean_win_rate)
      close(d.market_expected_rate, want[i].market_expected_rate)
      close(d.log_loss, want[i].log_loss)
      close(d.market_log_loss, want[i].market_log_loss)
    })
    const b = c.evaluate.bets
    expect([ev.bets.n, ev.bets.wins, ev.bets.losses]).toEqual([b.n, b.wins, b.losses])
    close(ev.bets.units, b.units)
    close(ev.bets.roi, b.roi)
    expect(Object.keys(ev.bets.by_season).sort()).toEqual(Object.keys(b.by_season).sort())
    for (const [s, u] of Object.entries(b.by_season)) close(ev.bets.by_season[Number(s)], u as number)
  })

  it('accuracy and reliability bins', () => {
    close(ev.overall.accuracy, c.extras.accuracy)
    close(ev.overall.market_accuracy, c.extras.market_accuracy)
    expect(ev.overall.n_market).toBe(c.extras.n_market)
    expect(ev.reliability.map((r) => [r.bin, r.n])).toEqual(c.extras.reliability.map((r: any) => [r.bin, r.n]))
    ev.reliability.forEach((r, i) => {
      close(r.mean_p, c.extras.reliability[i].mean_p)
      close(r.hit_rate, c.extras.reliability[i].hit_rate)
    })
  })

  it('per-game probabilities for one season', () => {
    const want = c.season
    const got = seasonPredictions(c.weights, matrix, want.season)
    expect(got.game_id).toEqual(want.game_id)
    got.p.forEach((p, i) => close(p, want.p[i]))
    close(got.calib_a, want.a)
    close(got.calib_c, want.c)
  })

  it('fit toward you reaches the same optimum', () => {
    if (!c.fit_toward) return
    const t = fitToward(c.weights, matrix, { maxSeason: c.max_season })
    const w = c.fit_toward
    // L-BFGS-B stops at a loose tolerance, so compare shares of the 100-point budget to 0.01
    for (const [g, v] of Object.entries(w.shares)) close(t.shares[g], v as number, 0.01)
    for (const [g, v] of Object.entries(w.user_shares)) close(t.user_shares[g], v as number, 1e-6)
    for (const [g, v] of Object.entries(w.user_scaled)) close(t.user_scaled[g], v as number, 1e-6)
  })
})
