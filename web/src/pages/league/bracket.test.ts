import { describe, expect, it } from 'vitest'
import type { LeagueOddsTeam } from '../../data/contract'
import { projectConference, projectSeeds, superBowl, type OddsMap } from './bracket'

const o = (seed: number[], r: { div?: number; conf?: number; sb?: number; champ?: number } = {}): LeagueOddsTeam => ({
  playoffs: seed.reduce((a, b) => a + b, 0), division: 0, bye: seed[0] ?? 0, seed: [...seed, 0, 0, 0, 0, 0, 0, 0].slice(0, 7),
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
