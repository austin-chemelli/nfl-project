import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import * as C from './contract'

const REAL = path.resolve(import.meta.dirname, '../../../data/marts/site')
const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site')

function schemaFor(rel: string) {
  const base = path.basename(rel)
  if (rel.startsWith('game/')) return C.Game
  if (rel.startsWith('retro/')) return C.RetroGame
  if (base.startsWith('recap_')) return C.WeekRecap
  if (base === 'meta.json') return C.Meta
  if (base.startsWith('slate_')) return C.Slate
  if (base === 'tracker.json') return C.Tracker
  if (base === 'hypotheses.json') return C.Hypotheses
  if (base === 'coaches.json') return C.Coaches
  if (base === 'diy_matrix.json') return C.DiyMatrix
  if (base.startsWith('season_')) return C.SeasonFile
  if (base === 'audit.json') return C.Audit
  return null
}

function files(root: string): string[] {
  if (!fs.existsSync(root)) return []
  const out: string[] = []
  for (const f of fs.readdirSync(root)) if (f.endsWith('.json')) out.push(f)
  const g = path.join(root, 'game')
  if (fs.existsSync(g)) for (const f of fs.readdirSync(g)) if (f.endsWith('.json')) out.push(`game/${f}`)
  const r = path.join(root, 'retro')
  if (fs.existsSync(r)) for (const f of fs.readdirSync(r)) if (f.endsWith('.json')) out.push(`retro/${f}`)
  return out
}

function check(root: string, rel: string) {
  const schema = schemaFor(rel)
  if (!schema) return
  const parsed = schema.safeParse(JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8')))
  if (!parsed.success) {
    const issues = parsed.error.issues.slice(0, 5).map((i) => `${i.path.join('.')}: ${i.message}`)
    expect.fail(`${rel}\n  ${issues.join('\n  ')}`)
  }
}

describe('contract: checked-in fixtures', () => {
  const fx = files(FIX)
  it('has fixtures for every page', () => expect(fx.length).toBeGreaterThan(5))
  it('parses a schema-1 retro without league bands (published before M10)', () => {
    const r = JSON.parse(fs.readFileSync(path.join(FIX, 'retro/2026_08_CAR_GB.json'), 'utf8'))
    r.schema_version = '1'
    for (const t of [r.teams.home, r.teams.away]) for (const e of t.efficiency) { delete e.league_lo; delete e.league_hi }
    const parsed = C.RetroGame.parse(r)
    expect(parsed.teams.home.efficiency[0]).toMatchObject({ league_lo: null, league_hi: null })
  })
  for (const rel of fx) it(rel, () => check(FIX, rel))
})

describe.skipIf(!fs.existsSync(REAL))('contract: local data/marts/site', () => {
  for (const rel of files(REAL)) it(rel, () => check(REAL, rel))
})
