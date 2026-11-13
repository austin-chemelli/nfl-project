import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { GameHealth, TeamHealth } from './contract'

const fixture = path.resolve(import.meta.dirname, '../test/fixtures/site/team_health_WAS.json')

describe('team health contract (M24.7)', () => {
  it('parses the pipeline output: full-strength starters, groups, by week, outlook', () => {
    const h = TeamHealth.parse(JSON.parse(fs.readFileSync(fixture, 'utf8')))
    const ir = h.now.starters.filter((s) => s.reserve).map((s) => s.player)
    expect(ir).toEqual(expect.arrayContaining(['Terry McLaurin', 'Laremy Tunsil', 'Daron Payne']))
    expect(h.now.health).toBeGreaterThan(0)
    expect(h.now.health).toBeLessThan(1)
    expect(h.by_week.length).toBeGreaterThan(0)
    expect(h.outlook.every((o) => o.week > h.now.week)).toBe(true)
  })

  it('keeps a game side null when that team plays another week first', () => {
    const g = GameHealth.parse({ home: { health: 0.8, missing_pts: 2.3, full_pts: 12 } })
    expect(g.away).toBeNull()
  })
})
