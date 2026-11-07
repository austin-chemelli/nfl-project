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
  if (base === 'teams.json') return C.TeamsFile
  if (base === 'league.json') return C.LeagueFile
  if (base === 'similar.json') return C.SimilarFile
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

describe('contract: league.json', () => {
  const raw = () => JSON.parse(fs.readFileSync(path.join(FIX, 'league.json'), 'utf8'))

  it('parses the fixture: 32 teams, both variants, at least 20 games', () => {
    const f = C.LeagueFile.parse(raw())
    expect(f.teams).toHaveLength(32)
    for (const v of [f.odds.student, f.odds.market]) {
      expect(Object.keys(v.teams)).toHaveLength(32)
      for (const o of Object.values(v.teams)) expect(o.seed).toHaveLength(7)
    }
    expect(f.games.length).toBeGreaterThanOrEqual(20)
  })

  it('keeps source counts as a record, whatever the keys', () => {
    const f = raw()
    f.odds.student.sources = { locked: 1, something_new: 2 }
    expect(C.LeagueFile.parse(f).odds.student.sources).toEqual({ locked: 1, something_new: 2 })
  })

  it('defaults empty swings, history and a missing seed_today', () => {
    const f = raw()
    delete f.games[0].swings
    delete f.history
    delete f.teams[0].seed_today
    const p = C.LeagueFile.parse(f)
    expect(p.games[0].swings).toEqual([])
    expect(p.history).toEqual({})
    expect(p.teams[0].seed_today).toBeNull()
  })

  it('types history', () => {
    const p = C.LeagueFile.parse(raw())
    expect(p.history.CHI).toHaveLength(3)
  })

  it('rejects a file without odds', () => {
    const f = raw()
    delete f.odds
    expect(C.LeagueFile.safeParse(f).success).toBe(false)
  })
})

describe('contract: teams.json', () => {
  const team = (code: string) => ({
    conference: code === 'KC' || code === 'BUF' ? 'AFC' : 'NFC',
    division: 'x',
    wins: 6,
    losses: 2,
    ties: 0,
    games_played: 8,
    points_for: 210,
    points_against: 160,
    last_game_id: '2026_08_A_B',
    next_game_id: '2026_09_A_B',
    games: [{ id: '2026_01_A_B', week: 1, opp: 'LAC', home: true, pf: 27, pa: 21 }, { id: '2026_09_A_B', week: 9, opp: 'NYJ', home: false, pf: null, pa: null }],
    values: { 'strength.epa_off': 0.1 },
    pct: { 'strength.epa_off': 87.1 },
    rank: { 'strength.epa_off': 5 },
  })
  const file = () => ({
    schema_version: '1',
    generated_at: '2026-11-05T23:02:08Z',
    season: 2026,
    week: 9,
    as_of: '2026-11-05T14:04:48Z',
    features: [{ id: 'strength.epa_off', label: 'EPA per play', short: 'Offense EPA', description: 'd', unit: 'epa', group: 'offense', group_name: 'Offense', better: 'higher', n: 4, mean: 0, lo: -0.1, q1: -0.05, med: 0, q3: 0.05, hi: 0.1 }],
    teams: Object.fromEntries(['KC', 'BUF', 'CHI', 'SF'].map((c) => [c, team(c)])),
  })

  it('parses a four-team file', () => expect(C.TeamsFile.safeParse(file()).success).toBe(true))

  it('defaults what a later contract added: games, points, next game, pct and rank', () => {
    const f = file()
    for (const t of Object.values(f.teams) as Partial<ReturnType<typeof team>>[]) {
      delete t.games
      delete t.points_for
      delete t.points_against
      delete t.next_game_id
      delete t.pct
      delete t.rank
    }
    const parsed = C.TeamsFile.parse(f)
    expect(parsed.teams.KC.games).toEqual([])
    expect(parsed.teams.KC.next_game_id).toBeNull()
    expect(parsed.teams.KC.rank).toBeUndefined()
  })

  it('accepts no direction and rejects an unknown one', () => {
    const f = file()
    f.features[0].better = null as unknown as string
    expect(C.TeamsFile.safeParse(f).success).toBe(true)
    f.features[0].better = 'sideways'
    expect(C.TeamsFile.safeParse(f).success).toBe(false)
  })
})

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
  it('a retro parses with wp_series and drives missing, null or filled (schema 6, additive)', () => {
    const r = JSON.parse(fs.readFileSync(path.join(FIX, 'retro/2026_08_CAR_GB.json'), 'utf8'))
    expect(C.RetroGame.parse(r).wp_series?.plays).toHaveLength(3)
    const { wp_series: _w, drives: _d, ...old } = r
    const parsed = C.RetroGame.parse(old)
    expect(parsed.wp_series ?? null).toBeNull()
    expect(parsed.drives ?? null).toBeNull()
    expect(C.RetroGame.parse({ ...old, wp_series: null, drives: null }).wp_series).toBeNull()
    const drive = { n: 1, team: 'GB', qtr: 1, t0: 0, t1: 171, start_yl: 25, end_yl: null, plays: 6, result: 'Punt' }
    expect(C.RetroGame.parse({ ...old, drives: [drive] }).drives?.[0]).toMatchObject(drive)
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

describe('contract: similar.json', () => {
  const raw = () => JSON.parse(fs.readFileSync(path.join(FIX, 'similar.json'), 'utf8'))
  it('parses the fixture: 25 nearest, flags, a pool, old team codes kept', () => {
    const p = C.SimilarFile.parse(raw())
    expect(p.measures).toHaveLength(7)
    expect(p.teams.CHI.nearest).toHaveLength(25)
    expect(p.teams.CHI.pool).toEqual({ seasons: [2002, 2025], n: 768 })
    expect(p.teams.CHI.flags[0].flagged).toEqual([11, 28])
    expect(p.teams.CHI.nearest.map((n) => n.team)).toEqual(expect.arrayContaining(['SD', 'OAK', 'STL']))
    expect(p.teams.DET.flags).toEqual([])
    expect(p.teams.NO).toBeUndefined()
  })
  it('defaults a missing round and flags', () => {
    const f = raw()
    delete f.teams.CHI.nearest[0].round
    delete f.teams.CHI.flags
    const p = C.SimilarFile.parse(f)
    expect(p.teams.CHI.nearest[0].round).toBeNull()
    expect(p.teams.CHI.flags).toEqual([])
  })
  it('rejects an entry without its summary or a flag with an unknown kind', () => {
    const f = raw()
    delete f.teams.CHI.made_playoffs
    expect(C.SimilarFile.safeParse(f).success).toBe(false)
    const g = raw()
    g.teams.CHI.flags[0].kind = 'purple'
    expect(C.SimilarFile.safeParse(g).success).toBe(false)
  })
  it('is no longer part of league.json', () => {
    expect('similar' in raw()).toBe(false)
    expect('similar' in JSON.parse(fs.readFileSync(path.join(FIX, 'league.json'), 'utf8'))).toBe(false)
  })
})

describe('contract: team files', () => {
  const dir = path.join(FIX, 'team')
  const load = (code: string) => C.TeamFile.parse(JSON.parse(fs.readFileSync(path.join(dir, `${code}.json`), 'utf8')))
  it('parses every fixture', () => {
    const files = fs.readdirSync(dir)
    expect(files.length).toBeGreaterThanOrEqual(2)
    for (const f of files) expect(load(f.replace('.json', '')).team).toBe(f.replace('.json', ''))
  })
  it('carries the ranks: LAC motion from 22nd to 3rd', () => {
    const row = load('LAC').units.off.live.find((m) => m.metric === 'motion_rate')
    expect(row?.observed?.rank).toBe(3)
    expect(row?.team_last?.rank).toBe(22)
  })
  it('names no unconfirmed play-caller in the staff lists', () => {
    for (const code of ['LAC', 'CAR']) {
      const { staff } = load(code)
      for (const s of [...staff.current, ...staff.changes]) if (s.role.endsWith('_PC')) expect(s.confirmed).toBe(true)
    }
  })
})

