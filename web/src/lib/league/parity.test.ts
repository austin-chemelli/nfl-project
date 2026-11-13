/**
 * The browser engine against the Python one (M26.3). Fixtures: scripts/league_parity.py.
 * - every 2002-2025 conference-season seeds as the Python does (with and without the points steps);
 * - 240 perturbed seasons (no scores, the simulation's case) reach the same seeds;
 * - 60 simulated runs replayed on the Python's draws give the same seeds and champion run for run;
 * - 4,000 runs on our own generator land within Monte Carlo error of the Python's odds.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import type { Conf } from './divisions'
import { fromScores, Results, type GameResult } from './standings'
import { seedConference, type Trace } from './tiebreak'
import { simulateSeason, type SimInput } from './simulate'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/league_parity')
const read = (f: string) => JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8'))
const noCoin = () => {
  throw new Error('coin flip: not comparable with the Python')
}

type Season = {
  season: number
  n_seeds: 6 | 7
  games: [string, string, number, number][]
  seeds: Record<Conf, string[]>
  seeds_capped: Record<Conf, string[]>
  perturbed: { outcomes: string; seeds: Record<Conf, string[]> | null; steps: string[] }[]
}

describe('tiebreak parity with the Python, 2002-2025', () => {
  const seasons: Season[] = read('seasons.json').seasons

  it('covers 24 seasons and every wild-card and division step the simulation can reach', () => {
    expect(seasons).toHaveLength(24)
    const steps = new Set(seasons.flatMap((s) => s.perturbed.flatMap((p) => p.steps)))
    for (const s of ['h2h', 'division', 'common', 'conference', 'sov', 'sos', 'common4', 'h2h_sweep']) expect(steps).toContain(s)
  })

  it('seeds every real conference-season like the Python, with and without scores', () => {
    for (const s of seasons) {
      const scored = new Results(s.games.map(([h, a, hs, as]) => fromScores(h, a, hs, as)))
      const capped = new Results(s.games.map(([h, a, hs, as]): GameResult => ({ home: h, away: a, outcome: hs > as ? 1 : hs < as ? 0 : 0.5 })))
      for (const c of ['AFC', 'NFC'] as Conf[]) {
        expect(seedConference(scored, c, noCoin, s.n_seeds), `${s.season} ${c}`).toEqual(s.seeds[c])
        expect(seedConference(capped, c, noCoin, s.n_seeds), `${s.season} ${c} capped`).toEqual(s.seeds_capped[c])
      }
    }
  })

  it('seeds every perturbed season like the Python', () => {
    let n = 0
    for (const s of seasons) {
      for (const p of s.perturbed) {
        if (!p.seeds) continue
        const r = new Results(s.games.map(([h, a], i): GameResult => ({ home: h, away: a, outcome: p.outcomes[i] === 'H' ? 1 : p.outcomes[i] === 'A' ? 0 : 0.5 })))
        const trace: Trace = []
        for (const c of ['AFC', 'NFC'] as Conf[]) expect(seedConference(r, c, noCoin, s.n_seeds, trace), `${s.season} ${c}`).toEqual(p.seeds[c])
        n++
      }
    }
    expect(n).toBeGreaterThanOrEqual(200)
  })
})

describe('simulation parity with the Python', () => {
  const fx = read('sim.json')
  const sc = fx.scenario
  const input: SimInput = {
    played: sc.played.map((g: { home: string; away: string; home_score: number; away_score: number }) => fromScores(g.home, g.away, g.home_score, g.away_score)),
    games: sc.games,
    ratings: sc.ratings,
    homeAdv: sc.home_adv,
    sigma: sc.sigma,
  }

  it('replays the Python draws run for run: same seeds, same champion', () => {
    const runs: { AFC: string[]; NFC: string[]; champ: string; coin: boolean }[] = fx.runs
    const got: typeof runs = []
    simulateSeason(input, {
      nRuns: runs.length,
      draws: (i) => ({ delta: fx.draws.delta[i], uGames: fx.draws.u_games[i], uBracket: fx.draws.u_bracket[i] }),
      onRun: (_, seeds, champ) => got.push({ AFC: seeds.AFC, NFC: seeds.NFC, champ, coin: false }),
    })
    const compared = runs.map((r, i) => [r, got[i]] as const).filter(([r]) => !r.coin)
    expect(compared.length).toBeGreaterThanOrEqual(50)
    for (const [want, have] of compared) expect(have).toEqual(want)
  })

  it('on its own generator, lands within Monte Carlo error of the Python odds', () => {
    const n = 4000
    const odds = simulateSeason(input, { nRuns: n, seed: 11 })
    for (const [t, py] of Object.entries(fx.stat.teams as Record<string, { playoffs: number; bye: number; champ: number; wins_mean: number }>)) {
      // two independent samples of 4,000: 4.5 standard errors of the difference
      const tol = (p: number) => 4.5 * Math.sqrt((2 * Math.max(p * (1 - p), 0.0025)) / n)
      expect(Math.abs(odds[t].playoffs - py.playoffs), `${t} playoffs`).toBeLessThan(tol(py.playoffs))
      expect(Math.abs(odds[t].bye - py.bye), `${t} bye`).toBeLessThan(tol(py.bye))
      expect(Math.abs(odds[t].rounds.champ - py.champ), `${t} champ`).toBeLessThan(tol(py.champ))
      expect(Math.abs(odds[t].winsMean - py.wins_mean), `${t} wins`).toBeLessThan(0.15)
    }
    const total = Object.values(odds).reduce((s, o) => s + o.playoffs, 0)
    expect(total).toBeCloseTo(14, 6)
  })

  it('a decided game is always won by the chosen team, and the same seed gives the same odds', () => {
    const g = input.games[0]
    const decided = new Map([[g.id, 'away' as const]])
    const a = simulateSeason(input, { nRuns: 300, seed: 5, decided })
    const b = simulateSeason(input, { nRuns: 300, seed: 5, decided })
    expect(a).toEqual(b)
    const now = simulateSeason(input, { nRuns: 300, seed: 5 })
    expect(a[g.away].winsMean).toBeGreaterThanOrEqual(now[g.away].winsMean)
    expect(a[g.home].winsMean).toBeLessThanOrEqual(now[g.home].winsMean)
  })
})
