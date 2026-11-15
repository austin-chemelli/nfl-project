import { describe, expect, it } from 'vitest'
import type { LeagueOddsTeam } from '../../data/contract'
import { projectConference, projectField, projectSeeds, superBowl, type OddsMap } from './bracket'

const o = (seed: number[], r: { div?: number; conf?: number; sb?: number; champ?: number } = {}, division = 0): LeagueOddsTeam => ({
  playoffs: seed.reduce((a, b) => a + b, 0), division, bye: seed[0] ?? 0, seed: [...seed, 0, 0, 0, 0, 0, 0, 0].slice(0, 7),
  rounds: { div: r.div ?? 0, conf: r.conf ?? 0, sb: r.sb ?? 0, champ: r.champ ?? 0 }, wins: { mean: 9, lo: 8, hi: 10 },
})

describe('projectSeeds', () => {
  it('gives each seed to one team, maximizing the summed chances, not seed by seed', () => {
    // A leads seed 1 and seed 2; B is nearly as good at seed 1 but useless at 2: greedy per seed would put A at 1 and leave 2 weak
    const odds: OddsMap = {
      A: o([0.5, 0.45]), B: o([0.48, 0.0]), C: o([0, 0.3, 0.2]), D: o([0, 0, 0.5]), E: o([0, 0, 0, 0.6]), F: o([0, 0, 0, 0, 0.5]), G: o([0, 0, 0, 0, 0, 0.5]), H: o([0, 0, 0, 0, 0, 0, 0.4]), I: o([0, 0, 0, 0, 0, 0, 0.1]),
    }
    const seeds = projectSeeds(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'], odds)
    expect(seeds).toEqual(['B', 'A', 'D', 'E', 'F', 'G', 'H'])
    expect(new Set(seeds).size).toBe(7)
  })

  it('fills every seed even when some teams have no chance at any', () => {
    const odds: OddsMap = Object.fromEntries('ABCDEFGH'.split('').map((t, i) => [t, o(i < 7 ? Array.from({ length: 7 }, (_, k) => (k === i ? 0.6 : 0.01)) : [])]))
    expect(projectSeeds('HGFEDCBA'.split(''), odds)).toEqual('ABCDEFG'.split(''))
  })
})

describe('projectField', () => {
  // The market NFC of 2026-11-15, rounded: the unconstrained seeding put NYG 3 and DAL 4 (both NFC East),
  // and left the NFC South out.
  const nfc: OddsMap = {
    SF: o([0.38, 0.34, 0.05, 0.01, 0.05, 0.06, 0.05], {}, 0.78), DET: o([0.23, 0.16, 0.01, 0, 0.2, 0.15, 0.1], {}, 0.41),
    MIN: o([0.17, 0.12, 0.01, 0, 0.23, 0.16, 0.12], {}, 0.31), CHI: o([0.12, 0.09, 0, 0, 0.2, 0.19, 0.15], {}, 0.22),
    SEA: o([0.03, 0.09, 0.02, 0, 0.09, 0.15, 0.17], {}, 0.14), GB: o([0.03, 0.04, 0, 0, 0.11, 0.15, 0.17], {}, 0.07),
    NYG: o([0.01, 0.03, 0.25, 0.15, 0, 0.01, 0.02], {}, 0.44), DAL: o([0, 0.03, 0.19, 0.2, 0, 0.01, 0.02], {}, 0.42),
    LA: o([0.02, 0.04, 0.01, 0, 0.1, 0.11, 0.13], {}, 0.08), CAR: o([0, 0.02, 0.16, 0.19, 0, 0, 0.01], {}, 0.38),
    ATL: o([0, 0.01, 0.1, 0.13, 0, 0.01, 0.01], {}, 0.24), TB: o([0, 0, 0.08, 0.16, 0, 0, 0.01], {}, 0.24),
    WAS: o([0, 0, 0.05, 0.05, 0, 0, 0.01], {}, 0.11), PHI: o([0, 0, 0.01, 0.02, 0, 0, 0], {}, 0.03),
  }
  const div: Record<string, string> = {
    SF: 'W', SEA: 'W', LA: 'W', DET: 'N', MIN: 'N', CHI: 'N', GB: 'N', NYG: 'E', DAL: 'E', WAS: 'E', PHI: 'E', CAR: 'S', ATL: 'S', TB: 'S',
  }
  const teams = Object.keys(nfc).map((team) => ({ team, div: div[team] }))

  it('regression: the unconstrained seeding puts two NFC East teams in seeds 3-4 and no NFC South team', () => {
    const old = projectSeeds(Object.keys(nfc), nfc)
    expect(old.slice(2, 4)).toEqual(['NYG', 'DAL'])
    expect(old.filter((t) => div[t] === 'S')).toEqual([])
  })

  it('one winner per division in seeds 1-4, wild cards by playoff chance in 5-7', () => {
    const f = projectField(teams, nfc)
    expect(f.seeds).toEqual(['DET', 'SF', 'NYG', 'CAR', 'MIN', 'CHI', 'SEA'])
    expect(new Set(f.seeds.slice(0, 4).map((t) => div[t])).size).toBe(4)
    expect(f.divWinner).toEqual({ W: 'SF', N: 'DET', E: 'NYG', S: 'CAR' })
    expect(f.out.slice(0, 3)).toEqual(['GB', 'DAL', 'LA'])
    // every wild card is at least as likely to make the playoffs as every team left out
    const minWild = Math.min(...f.seeds.slice(4).map((t) => nfc[t].playoffs))
    expect(Math.max(...f.out.map((t) => nfc[t].playoffs))).toBeLessThanOrEqual(minWild)
  })

  it('a wild card whose chances sit in the top seeds still beats a long shot (KC over CLE)', () => {
    // KC mostly wins its division or nothing; the per-seed sum dropped it for a 32% team
    const odds: OddsMap = {
      BUF: o([0.6, 0.3, 0.05], {}, 0.9), JAX: o([0.2, 0.3, 0.3, 0.1], {}, 0.9), DEN: o([0.1, 0.2, 0.3, 0.2, 0.05], {}, 0.6),
      CIN: o([0.05, 0.1, 0.2, 0.4, 0.05], {}, 0.6), KC: o([0.05, 0.1, 0.15, 0.2, 0.1, 0.1, 0.05], {}, 0.4),
      NE: o([0, 0, 0, 0, 0.4, 0.3, 0.1], {}, 0.05), PIT: o([0, 0, 0, 0, 0.3, 0.3, 0.2], {}, 0.05), CLE: o([0, 0, 0, 0, 0.05, 0.1, 0.17], {}, 0),
    }
    const d: Record<string, string> = { BUF: 'E', NE: 'E', JAX: 'S', DEN: 'W', KC: 'W', CIN: 'N', PIT: 'N', CLE: 'N' }
    expect(projectSeeds(Object.keys(odds), odds)).toContain('CLE')
    const f = projectField(Object.keys(odds).map((team) => ({ team, div: d[team] })), odds)
    expect(f.seeds).toContain('KC')
    expect(f.out).toEqual(['CLE'])
  })
})

describe('projectConference', () => {
  const odds: OddsMap = {
    S1: o([1], { div: 0.9, conf: 0.5, sb: 0.2 }), S2: o([0, 1], { div: 0.7, conf: 0.4, sb: 0.3 }), S3: o([0, 0, 1], { div: 0.4, conf: 0.6, sb: 0.25 }),
    S4: o([0, 0, 0, 1], { div: 0.6, conf: 0.2 }), S5: o([0, 0, 0, 0, 1], { div: 0.5, conf: 0.1 }), S6: o([0, 0, 0, 0, 0, 1], { div: 0.5, conf: 0.3 }), S7: o([0, 0, 0, 0, 0, 0, 1], { div: 0.2 }),
  }
  const b = projectConference(['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'], odds)

  it('pairs 2-7, 3-6, 4-5 with a bye for the 1 seed, the better seed listed first', () => {
    expect(b.bye.map((s) => s.team)).toEqual(['S1'])
    expect(b.wildCard.map((g) => [g.a.team, g.b.team])).toEqual([['S2', 'S7'], ['S3', 'S6'], ['S4', 'S5']])
  })

  it('advances the team more likely to reach the next round, and reseeds so the 1 seed meets the lowest left', () => {
    expect(b.wildCard.map((g) => g.winner.team)).toEqual(['S2', 'S6', 'S4']) // S6 0.5 > S3 0.4
    expect(b.divisional.map((g) => [g.a.team, g.b.team])).toEqual([['S1', 'S6'], ['S2', 'S4']])
    expect(b.divisional.map((g) => g.winner.team)).toEqual(['S1', 'S2'])
    expect(b.champ.team).toBe('S2') // sb 0.3 > 0.2
  })

  it('six seeds: two byes and 3-6, 4-5', () => {
    const six = projectConference(['S1', 'S2', 'S3', 'S4', 'S5', 'S6'], odds)
    expect(six.bye.map((s) => s.team)).toEqual(['S1', 'S2'])
    expect(six.wildCard.map((g) => [g.a.team, g.b.team])).toEqual([['S3', 'S6'], ['S4', 'S5']])
  })

  it('the Super Bowl goes to the more likely champion', () => {
    const sb = superBowl({ team: 'A', seed: 1 }, { team: 'N', seed: 3 }, { A: o([], { champ: 0.1 }), N: o([], { champ: 0.12 }) })
    expect(sb.winner.team).toBe('N')
  })
})

describe('records', () => {
  it('projects a final record from expected wins and keeps it possible', async () => {
    const { projected, recordView } = await import('./bracket')
    expect(projected({ w: 7, l: 2, t: 0, left: 8 }, 11.6)).toEqual({ w: 12, l: 5, t: 0 })
    expect(projected({ w: 7, l: 2, t: 0, left: 8 }, 3)).toEqual({ w: 7, l: 10, t: 0 }) // never fewer wins than now
    expect(projected({ w: 5, l: 2, t: 1, left: 9 }, 10.5)).toEqual({ w: 10, l: 6, t: 1 })
    const r = recordView({ team: 'DAL', w: 4, l: 5, t: 0, left: 8 }, [
      { home: 'DAL', away: 'SF', winner: 'home' }, { home: 'PHI', away: 'DAL', winner: 'home' }, { home: 'KC', away: 'BUF', winner: 'away' },
    ], 9.2, 8.1)
    expect(r.now).toEqual({ w: 5, l: 6, t: 0 })
    expect(r.added).toEqual({ w: 1, l: 1 })
    expect(r.proj).toEqual({ w: 9, l: 8, t: 0 })
    expect(r.projWas).toEqual({ w: 8, l: 9, t: 0 })
  })
})
