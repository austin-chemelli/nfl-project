import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile, TeamsFile } from '../../data/contract'
import {
  compareDomain,
  compareGroups,
  edgeOf,
  firstSort,
  hasSpark,
  rankColumns,
  resolveVs,
  shadeFor,
  sortTeams,
  sparkLabel,
  sparkSeries,
} from './context'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'league.json'), 'utf8')))
const teams = TeamsFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'teams.json'), 'utf8')))

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
    const [l0, l1] = compareDomain(teams, lower)
    const [h0, h1] = compareDomain(teams, higher)
    expect(l0).toBeGreaterThan(l1)
    expect(h0).toBeLessThan(h1)
  })

  it('spans the true league range, whoever the opponent is', () => {
    const rows = compareGroups(teams, 'KC', 'BUF').flatMap((g) => g.rows)
    const r = rows.find((x) => x.feature.better === 'higher')!
    const all = Object.values(teams.teams).map((t) => t.values[r.feature.id]).filter((v): v is number => v != null)
    expect(compareDomain(teams, r)).toEqual([Math.min(...all), Math.max(...all)])
    const other = compareGroups(teams, 'KC', 'MIA').flatMap((g) => g.rows).find((x) => x.feature.id === r.feature.id)!
    expect(compareDomain(teams, other)).toEqual(compareDomain(teams, r))
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
