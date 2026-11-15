/**
 * The playoff odds and the projected field against the NFL's rule that each division sends exactly one
 * winner to seeds 1-4 (bracket fix, Austin 2026-11-15). Checked on the published fixture and on the
 * browser engine in several what-if scenarios: the odds must add up the way the rule forces, and the
 * projected field must be valid and agree with the odds.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import type { LeagueOddsTeam } from '../../data/contract'
import { DIVISIONS, TEAMS } from '../../lib/league/divisions'
import { simulateSeason, type SimInput } from '../../lib/league/simulate'
import { fromScores, Results } from '../../lib/league/standings'
import { seedConference } from '../../lib/league/tiebreak'
import { projectField, type OddsMap } from './bracket'
import { toOddsTeam } from './whatif'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures')
const read = (f: string) => JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8'))
const EPS = 0.002
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)

/** Every identity the one-winner-per-division rule implies, as a list of failures. */
function ruleFailures(odds: OddsMap, nSeeds = 7): string[] {
  const bad: string[] = []
  const teams = TEAMS.filter((t) => odds[t])
  const divs = new Map<string, string[]>()
  for (const t of teams) divs.set(DIVISIONS[t][1], [...(divs.get(DIVISIONS[t][1]) ?? []), t])
  for (const [div, ts] of divs) {
    if (Math.abs(sum(ts.map((t) => odds[t].division)) - 1) > EPS) bad.push(`${div}: P(win division) sums to ${sum(ts.map((t) => odds[t].division))}`)
  }
  for (const conf of ['AFC', 'NFC']) {
    const ts = teams.filter((t) => DIVISIONS[t][0] === conf)
    for (let k = 0; k < nSeeds; k++) if (Math.abs(sum(ts.map((t) => odds[t].seed[k])) - 1) > EPS) bad.push(`${conf} seed ${k + 1} doesn't sum to 1`)
    if (Math.abs(sum(ts.map((t) => odds[t].playoffs)) - nSeeds) > 0.01) bad.push(`${conf}: playoffs don't sum to ${nSeeds}`)
  }
  for (const t of teams) {
    const o = odds[t]
    if (Math.abs(o.playoffs - sum(o.seed)) > EPS) bad.push(`${t}: playoffs != sum of seeds`)
    if (Math.abs(o.division - sum(o.seed.slice(0, 4))) > EPS) bad.push(`${t}: division != seeds 1-4`)
    if (Math.abs(o.bye - o.seed[0]) > EPS) bad.push(`${t}: bye != seed 1`)
    const r = o.rounds
    if (!(o.playoffs + 1e-9 >= r.div && r.div >= r.conf && r.conf >= r.sb && r.sb >= r.champ)) bad.push(`${t}: rounds not decreasing`)
  }
  return bad
}

/** The projected field is valid and agrees with the odds. */
function expectValidField(odds: OddsMap) {
  for (const conf of ['AFC', 'NFC']) {
    const teams = TEAMS.filter((t) => DIVISIONS[t][0] === conf && odds[t]).map((team) => ({ team, div: DIVISIONS[team][1] }))
    const f = projectField(teams, odds)
    expect(new Set(f.seeds).size).toBe(7)
    const top = f.seeds.slice(0, 4).map((t) => DIVISIONS[t][1])
    expect(new Set(top).size).toBe(4) // one winner per division
    for (const t of f.seeds.slice(4)) expect(Object.values(f.divWinner)).not.toContain(t)
    // each division's winner is its likeliest one
    for (const [div, w] of Object.entries(f.divWinner)) {
      for (const t of teams.filter((x) => x.div === div)) expect(odds[w].division).toBeGreaterThanOrEqual(odds[t.team].division - 1e-12)
    }
    // no wild card below a team left out
    const minWild = Math.min(...f.seeds.slice(4).map((t) => odds[t].playoffs))
    for (const t of f.out) expect(odds[t].playoffs).toBeLessThanOrEqual(minWild + 1e-12)
  }
}

const REAL = path.resolve(import.meta.dirname, '../../../../data/marts/site/league.json')

describe.skipIf(!fs.existsSync(REAL))('published odds obey the division rule', () => {
  const file = fs.existsSync(REAL) ? JSON.parse(fs.readFileSync(REAL, 'utf8')) : null
  for (const v of ['student', 'market'] as const) {
    it(v, () => {
      const odds: OddsMap = file.odds[v].teams
      expect(ruleFailures(odds)).toEqual([])
      expectValidField(odds)
    })
  }
})

describe('what-if odds obey the division rule', () => {
  const sc = read('league_parity/sim.json').scenario
  const input: SimInput = {
    played: sc.played.map((g: { home: string; away: string; home_score: number; away_score: number }) => fromScores(g.home, g.away, g.home_score, g.away_score)),
    games: sc.games,
    ratings: sc.ratings,
    homeAdv: sc.home_adv,
    sigma: sc.sigma,
  }
  type G = { id: string; home: string; away: string; p: number }
  const games: G[] = sc.games
  const run = (decided: Map<string, 'home' | 'away'>, nRuns = 2000): OddsMap =>
    Object.fromEntries(Object.entries(simulateSeason(input, { nRuns, seed: 7, decided })).map(([t, o]) => [t, toOddsTeam(o) as LeagueOddsTeam]))
  const nfcEast = new Set(['DAL', 'NYG', 'PHI', 'WAS'])
  const scenarios: [string, Map<string, 'home' | 'away'>][] = [
    ['nothing decided', new Map()],
    ['the first 20 games to the underdog', new Map(games.slice(0, 20).map((g) => [g.id, g.p >= 0.5 ? 'away' : 'home']))],
    ['NFC East games to the home team', new Map(games.filter((g) => nfcEast.has(g.home) && nfcEast.has(g.away)).map((g) => [g.id, 'home']))],
    ['every game to the favorite but one week', new Map(games.filter((_, i) => i % 16 !== 0).map((g) => [g.id, g.p >= 0.5 ? 'home' : 'away']))],
  ]
  for (const [name, decided] of scenarios) {
    it(name, () => {
      const odds = run(decided)
      expect(ruleFailures(odds)).toEqual([])
      expectValidField(odds)
    })
  }

  it('with every game decided, the projected field is the real seeding', () => {
    const decided = new Map(games.map((g) => [g.id, g.p >= 0.5 ? ('home' as const) : ('away' as const)]))
    const odds = run(decided, 200)
    expect(ruleFailures(odds)).toEqual([])
    const final = new Results([...input.played, ...games.map((g) => fromScores(g.home, g.away, decided.get(g.id) === 'home' ? 1 : 0, decided.get(g.id) === 'home' ? 0 : 1))])
    const coin = () => 0.5
    let compared = 0
    for (const conf of ['AFC', 'NFC'] as const) {
      const real = seedConference(final, conf, coin)
      // a coin-flip tiebreak can leave a seed split; only compare when every seed is settled
      const settled = real.every((t, k) => odds[t].seed[k] === 1)
      if (!settled) continue
      compared++
      const f = projectField(TEAMS.filter((t) => DIVISIONS[t][0] === conf).map((team) => ({ team, div: DIVISIONS[team][1] })), odds)
      expect(f.seeds).toEqual(real)
    }
    expect(compared).toBeGreaterThan(0)
  })
})
