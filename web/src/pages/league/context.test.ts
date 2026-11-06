import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile, TeamsFile, type SimilarTeam } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import {
  compareDomain,
  compareGroups,
  defaultSimilarTeam,
  edgeOf,
  firstSort,
  hasSpark,
  outcomeText,
  rankColumns,
  recordFrom,
  resolveSimilarTeam,
  resolveVs,
  shadeFor,
  similarHeadline,
  similarRows,
  similarTiles,
  sortTeams,
  sparkLabel,
  sparkSeries,
} from './context'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'league.json'), 'utf8')))
const teams = TeamsFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'teams.json'), 'utf8')))

const sim: SimilarTeam = {
  games_played: 8,
  k_summary: 25,
  made_playoffs: 9,
  rounds: { div: 4, conf: 2, sb: 1, champ: 0 },
  neighbours: [
    { season: 2018, team: 'CAR', dist: 0.79, rec_then: '6-2', final: '7-9-0', playoffs: false, round: null },
    { season: 2011, team: 'SD', dist: 0.8, rec_then: '5-3', final: '8-7-1', playoffs: true, round: 'wc' },
  ],
}

describe('similar seasons', () => {
  it('prints records with an en dash and drops a zero tie count', () => {
    expect(recordFrom('7-9-0')).toBe('7–9')
    expect(recordFrom('8-7-1')).toBe('8–7–1')
    expect(recordFrom('6-2')).toBe('6–2')
  })

  it('says the round reached in words, for every round and for a miss', () => {
    const o = (playoffs: boolean, round: string | null) => outcomeText({ playoffs, round })
    expect(o(false, null)).toBe('Missed the playoffs')
    expect(o(true, 'wc')).toBe('Lost in the wild-card round')
    expect(o(true, 'div')).toBe('Lost in the divisional round')
    expect(o(true, 'conf')).toBe('Lost the conference game')
    expect(o(true, 'sb')).toBe('Lost the Super Bowl')
    expect(o(true, 'champ')).toBe('Won the Super Bowl')
    expect(o(true, null)).toBe('Made the playoffs')
    expect(o(true, 'something-new')).toBe('Made the playoffs')
  })

  it('summarizes as counts of the nearest, not percentages', () => {
    expect(similarHeadline(sim)).toBe('9 of 25 made the playoffs')
    expect(similarTiles(sim).map((t) => [t.label, t.value])).toEqual([
      ['Made the playoffs', '9 of 25'],
      ['Reached the divisional round', '4 of 25'],
      ['Reached the conference game', '2 of 25'],
      ['Reached the Super Bowl', '1 of 25'],
      ['Won the Super Bowl', '0 of 25'],
    ])
  })

  it('builds the rows, keeping the team as printed', () => {
    expect(similarRows(sim).map((r) => [r.season, r.team, r.then, r.final, r.outcome])).toEqual([
      [2018, 'CAR', '6–2', '7–9', 'Missed the playoffs'],
      [2011, 'SD', '5–3', '8–7–1', 'Lost in the wild-card round'],
    ])
  })

  it('picks the best playoff chance among teams with an entry, and never a team without one', () => {
    const best = Object.keys(league.similar).sort((a, b) => league.odds.student.teams[b].playoffs - league.odds.student.teams[a].playoffs)[0]
    expect(defaultSimilarTeam(league)).toBe(best)
    expect(defaultSimilarTeam({ ...league, similar: {} })).toBeNull()
  })

  it('resolves ?team= to a team in the file, else the default; hasOwn guards the prototype', () => {
    expect(resolveSimilarTeam(league, 'MIA')).toBe('MIA')
    expect(resolveSimilarTeam(league, 'NO')).toBe('NO') // a real team with no entry stays picked
    expect(resolveSimilarTeam(league, 'constructor')).toBe(defaultSimilarTeam(league))
    expect(resolveSimilarTeam(league, null)).toBe(defaultSimilarTeam(league))
  })

  it('names old franchise codes as the franchise', () => {
    expect(teamInfo('SD').name).toBe('Los Angeles Chargers')
    expect(teamInfo('OAK').name).toBe('Las Vegas Raiders')
    expect(teamInfo('STL').name).toBe('Los Angeles Rams')
  })
})

describe('compare', () => {
  it('reads the better side by direction: lower is better, null has no edge', () => {
    expect(edgeOf({ better: 'higher' }, 5, 3)).toBe('a')
    expect(edgeOf({ better: 'lower' }, 5, 3)).toBe('b')
    expect(edgeOf({ better: 'lower' }, 3, 5)).toBe('a')
    expect(edgeOf({ better: null }, 5, 3)).toBeNull()
    expect(edgeOf({ better: 'higher' }, 4, 4)).toBeNull()
    expect(edgeOf({ better: 'higher' }, null, 4)).toBeNull()
  })

  it('groups every published measure in registry order, counting the edges', () => {
    const groups = compareGroups(teams, 'KC', 'BUF')
    expect(groups.map((g) => g.name)).toEqual(['Quality', 'Offense', 'Defense', 'Form', 'Coaching', 'Defensive scheme'])
    expect(groups.flatMap((g) => g.rows)).toHaveLength(17)
    for (const g of groups) {
      expect(g.aAhead + g.bAhead).toBeLessThanOrEqual(g.rows.length)
      for (const r of g.rows) {
        if (r.feature.better == null) expect(r.edge).toBeNull()
        else if (r.a != null && r.b != null && r.a !== r.b) expect(r.edge).toBe((r.feature.better === 'higher' ? r.a > r.b : r.a < r.b) ? 'a' : 'b')
      }
    }
    const quality = groups[0]
    expect(quality.aAhead).toBe(quality.rows.filter((r) => r.edge === 'a').length)
  })

  it('drops a measure neither team has, and a group left empty', () => {
    const f = structuredClone(teams)
    delete f.teams.KC.values['front.blitz_rate']
    delete f.teams.BUF.values['front.blitz_rate']
    const groups = compareGroups(f, 'KC', 'BUF')
    expect(groups.map((g) => g.name)).not.toContain('Defensive scheme')
    expect(compareGroups(teams, 'KC', 'NOPE')).toEqual([])
  })

  it('flips the axis where lower is better so right means better', () => {
    const rows = compareGroups(teams, 'KC', 'BUF').flatMap((g) => g.rows)
    const lower = rows.find((r) => r.feature.better === 'lower')!
    const higher = rows.find((r) => r.feature.better === 'higher')!
    const [l0, l1] = compareDomain(lower)
    const [h0, h1] = compareDomain(higher)
    expect(l0).toBeGreaterThan(l1)
    expect(h0).toBeLessThan(h1)
  })

  it('ignores an unknown, repeated or missing ?vs=', () => {
    expect(resolveVs(teams, 'KC', 'BUF')).toBe('BUF')
    expect(resolveVs(teams, 'KC', 'constructor')).toBeNull()
    expect(resolveVs(teams, 'KC', 'NOPE')).toBeNull()
    expect(resolveVs(teams, 'KC', 'KC')).toBeNull()
    expect(resolveVs(teams, null, 'BUF')).toBeNull()
  })
})

describe('rank table', () => {
  it('uses each preset measure once, only those with data', () => {
    const ids = rankColumns(teams).map((f) => f.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids[0]).toBe('strength.epa_off')
    expect(ids).toContain('form.epa_trend')
  })

  it('sorts by name, then by value with the best first on a first click', () => {
    const byName = sortTeams(teams, firstSort('team'))
    expect(byName).toHaveLength(32)
    expect(byName[0]).toBe('ARI')
    const def = teams.features.find((f) => f.id === 'strength.epa_def')!
    const best = sortTeams(teams, firstSort(def.id, def))
    const vals = best.map((c) => teams.teams[c].values[def.id])
    expect(vals).toEqual([...vals].sort((a, b) => a - b)) // lower defense EPA is better
    const high = sortTeams(teams, { key: def.id, dir: 'descending' })
    expect(high[0]).toBe(best[best.length - 1])
  })

  it('puts teams without a value last in either direction', () => {
    const f = structuredClone(teams)
    delete f.teams.ARI.values['strength.epa_off']
    expect(sortTeams(f, { key: 'strength.epa_off', dir: 'ascending' }).at(-1)).toBe('ARI')
    expect(sortTeams(f, { key: 'strength.epa_off', dir: 'descending' }).at(-1)).toBe('ARI')
  })

  it('shades best darkest and the worst not at all, none without a rank', () => {
    expect(shadeFor(1, 32)).toBe(45)
    expect(shadeFor(32, 32)).toBe(0)
    expect(shadeFor(16, 32)).toBeGreaterThan(shadeFor(17, 32)!)
    expect(shadeFor(undefined, 32)).toBeNull()
  })
})

describe('odds history', () => {
  it('reads the view\'s series in week order, skipping weeks without a value', () => {
    const f = structuredClone(league)
    f.history.CHI = [
      { week: 7, student: 0.8, market: null },
      { week: 5, student: 0.7, market: 0.6 },
      { week: 6, student: null, market: 0.65 },
    ]
    expect(sparkSeries(f, 'CHI', 'student')).toEqual([{ week: 5, value: 0.7 }, { week: 7, value: 0.8 }])
    expect(sparkSeries(f, 'CHI', 'market')).toEqual([{ week: 5, value: 0.6 }, { week: 6, value: 0.65 }])
    expect(sparkSeries(f, 'constructor', 'student')).toEqual([])
    expect(sparkSeries(f, 'NO', 'student')).toEqual([])
  })

  it('draws from two points', () => {
    expect(hasSpark([])).toBe(false)
    expect(hasSpark([{ week: 5, value: 0.5 }])).toBe(false)
    expect(hasSpark([{ week: 5, value: 0.5 }, { week: 6, value: 0.6 }])).toBe(true)
  })

  it('labels the first and last value, never 0% or 100%', () => {
    expect(sparkLabel([{ week: 5, value: 0.711 }, { week: 7, value: 0.9995 }])).toBe('Chance of the playoffs by week: Week 5 71%, Week 7 >99.9%')
  })
})
