import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile } from '../../data/contract'
import { simInputFrom } from './input'
import { runSimulation } from './client'

const base = LeagueFile.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../../test/fixtures/site/league.json'), 'utf8')))
const ratings = Object.fromEntries(base.teams.map((t, i) => [t.team, (i - 15.5) / 20]))
const withM262 = (): LeagueFile => ({
  ...base,
  through_week: 0,
  played: [],
  odds: { student: { ...base.odds.student, ratings, home_term: 0.1 }, market: { ...base.odds.market, ratings, home_term: 0.1 } },
})

describe('simInputFrom', () => {
  it('is null for a file from before M26.2 (no ratings, or no results for played weeks)', () => {
    expect(simInputFrom(base, 'student')).toBeNull()
    expect(simInputFrom({ ...withM262(), through_week: 9 }, 'student')).toBeNull()
  })

  it('takes each source its own chances and ratings', () => {
    const f = withM262()
    const s = simInputFrom(f, 'student')!
    const m = simInputFrom(f, 'market')!
    expect(s.games).toHaveLength(f.games.length)
    expect(s.games[0].p).toBe(f.games[0].p_student)
    expect(m.games[0].p).toBe(f.games[0].p_market)
    expect(s.sigma).toBe(f.shock_sigma)
    expect(s.homeAdv).toBe(0.1)
  })

  it('runs without a Worker (tests) and every team lands somewhere', async () => {
    const odds = await runSimulation(simInputFrom(withM262(), 'student')!, 200, 1)
    expect(Object.keys(odds)).toHaveLength(32)
    expect(Object.values(odds).reduce((s, o) => s + o.playoffs, 0)).toBeCloseTo(14, 6)
  })
})
