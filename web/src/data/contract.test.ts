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
  const raw = JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'))
  const parsed = schema.safeParse(raw)
  // GameRow forgives a bad card at runtime, so drift has to fail here
  for (const row of rel.startsWith('game/') ? [raw] : (raw.games ?? [])) {
    if (row.card == null) continue
    expect(C.CardData.safeParse(row.card).error?.issues).toBeUndefined()
    // these default to false, so a renamed flag would parse and quietly empty every card
    for (const i of row.card.injuries ?? []) expect(i).toEqual(expect.objectContaining({ starter: expect.any(Boolean), new: expect.any(Boolean) }))
  }
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
  it('a slate row parses with no card, an empty one, a partial one, and loses only the card when it is bad', () => {
    const row = JSON.parse(fs.readFileSync(path.join(FIX, 'slate_2026_08.json'), 'utf8')).games[0]
    const { card: _drop, ...bare } = row
    expect(C.GameRow.parse(bare).card).toBeNull()
    expect(C.GameRow.parse({ ...bare, card: null }).card).toBeNull()
    expect(C.GameRow.parse({ ...bare, card: {} }).card).toMatchObject({ edges: {}, injuries: [], usual_qb: { home: null, away: null }, charted_qb: { home: null, away: null }, contrast: null })
    expect(C.GameRow.parse({ ...bare, card: { injuries: [{ team: 'GB', player: 'A', pos: null, status: 'Out' }] } }).card?.injuries[0]).toMatchObject({ starter: false, new: false })
    expect(C.GameRow.parse({ ...bare, card: { injuries: null } }).card).toBeNull()
  })
  for (const rel of fx) it(rel, () => check(FIX, rel))
})

describe.skipIf(!fs.existsSync(REAL))('contract: local data/marts/site', () => {
  for (const rel of files(REAL)) it(rel, () => check(REAL, rel))
})

describe('contract: recap bold calls', () => {
  const raw = () => JSON.parse(fs.readFileSync(path.join(FIX, 'recap_2026_08.json'), 'utf8'))
  it('defaults both calls to null for a recap built before they existed', () => {
    const r = raw()
    delete r.best_call
    delete r.costliest_call
    const out = C.WeekRecap.parse(r)
    expect(out.best_call).toBeNull()
    expect(out.costliest_call).toBeNull()
  })
  it('parses a call, and keeps the ensemble kind readable', () => {
    expect(C.WeekRecap.parse(raw()).costliest_call).toMatchObject({ model_id: 'student', earned: -0.591 })
    const r = raw()
    r.models.push({ model_id: 'ensemble', label: 'Ensemble', kind: 'ensemble', n: 13, right: 9, log_loss: 0.6, vs_market: -0.02, rank: 1 })
    expect(C.WeekRecap.parse(r).models.some((m: { kind: string }) => m.kind === 'ensemble')).toBe(true)
  })
})
