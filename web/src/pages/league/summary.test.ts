import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile } from '../../data/contract'
import { closestRace, gameOfWeek, topSeed } from './summary'

const file = LeagueFile.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../../test/fixtures/site/league.json'), 'utf8')))

/** A tiny league: two divisions per the fields the tiles read. */
function tiny() {
  const row = (team: string, conf: string, div: string) => ({ team, conf, div, w: 1, l: 1, t: 0, pct: 0.5, div_rec: '0-0', conf_rec: '0-0', pf: 1, pa: 1, left: 1, div_rank: 1, seed_today: null })
  const odds = (playoffs: number, division: number, seed1: number) => ({ playoffs, division, bye: seed1, seed: [seed1, 0, 0, 0, 0, 0, 0], rounds: { div: 0, conf: 0, sb: 0, champ: 0 }, wins: { mean: 9, lo: 8, hi: 10 } })
  return LeagueFile.parse({
    schema_version: '1', season: 2026, generated_at: 'x', as_of: 'x', n_sims: 1, shock_sigma: 0.4,
    teams: [row('AAA', 'AFC', 'AFC East'), row('BBB', 'AFC', 'AFC East'), row('CCC', 'NFC', 'NFC North'), row('DDD', 'NFC', 'NFC North')],
    odds: {
      student: { teams: { AAA: odds(0.9, 0.7, 0.4), BBB: odds(0.3, 0.3, 0.1), CCC: odds(0.6, 0.45, 0.2), DDD: odds(0.5, 0.4, 0.3) } },
      market: { teams: { AAA: odds(0.85, 0.7, 0.4), BBB: odds(0.2, 0.3, 0.1), CCC: odds(0.4, 0.45, 0.2), DDD: odds(0.5, 0.4, 0.3) } },
    },
    games: [
      { game_id: 'a', week: 10, home: 'AAA', away: 'CCC', leverage_total: 9 },
      { game_id: 'b', week: 9, home: 'BBB', away: 'DDD', leverage_total: 0.2 },
      { game_id: 'c', week: 9, home: 'AAA', away: 'DDD', leverage_total: 0.5 },
    ],
  })
}

describe('summary tiles on a small league', () => {
  it('topSeed: the conference team with the highest P(seed 1)', () => {
    expect(topSeed(tiny(), 'AFC')).toEqual({ team: 'AAA', p: 0.4 })
    expect(topSeed(tiny(), 'NFC')).toEqual({ team: 'DDD', p: 0.3 })
  })
  it('closestRace: the division whose favorite is least likely to win it', () => {
    expect(closestRace(tiny())).toEqual({ division: 'NFC North', leader: { team: 'CCC', p: 0.45 }, runnerUp: { team: 'DDD', p: 0.4 } })
  })
  it('gameOfWeek: highest leverage among the earliest week, not the whole schedule', () => {
    expect(gameOfWeek(tiny(), 0)?.game_id).toBe('c')
  })
  it('gameOfWeek: a game already kicked off never counts, and a stuck week lets go', () => {
    const t = tiny()
    t.games = [
      { ...t.games[0], game_id: 'done', week: 9, kickoff: '2026-11-01T18:00:00Z', leverage_total: 0.9 },
      { ...t.games[0], game_id: 'next', week: 10, kickoff: '2026-11-08T18:00:00Z', leverage_total: 0.2 },
    ]
    expect(gameOfWeek(t, Date.parse('2026-11-02T00:00:00Z'))?.game_id).toBe('next')
  })
  it('return null when the file has nothing to say', () => {
    const t = tiny()
    t.games = []
    t.teams = []
    expect(gameOfWeek(t, 0)).toBeNull()
    expect(topSeed(t, 'AFC')).toBeNull()
    expect(closestRace(t)).toBeNull()
  })
})

describe('summary tiles on the fixture', () => {
  it('agree with a brute-force reading of the file', () => {
    for (const conf of ['AFC', 'NFC'] as const) {
      const best = Math.max(...file.teams.filter((t) => t.conf === conf).map((t) => file.odds.market.teams[t.team].seed[0]))
      expect(topSeed(file, conf)!.p).toBe(best)
    }
    const wk = Math.min(...file.games.map((g) => g.week))
    expect(gameOfWeek(file, 0)!.leverage_total).toBe(Math.max(...file.games.filter((g) => g.week === wk).map((g) => g.leverage_total)))
    const lowestLeader = Math.min(
      ...[...new Set(file.teams.map((t) => t.div))].map((d) => Math.max(...file.teams.filter((t) => t.div === d).map((t) => file.odds.market.teams[t.team].division))),
    )
    expect(closestRace(file)!.leader.p).toBe(lowestLeader)
  })
})
