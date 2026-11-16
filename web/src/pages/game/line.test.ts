import { describe, expect, it } from 'vitest'
import { cardMove, etDay, fmtPts, foldEvents, pathSentence, windowWords } from './line'

const move = (d: number | null) => ({ first_seen: '2026-10-27T22:46:59Z', latest: '2026-11-03T21:40:31Z', n_points: 10, lock_ts: null, since_first: d == null ? null : { spread_home: d, total: null, p_home: null, hours: 160 }, since_lock: null, last_day: null })

describe('line words', () => {
  it('names the team the line moved toward, and the day first seen in Eastern time', () => {
    expect(etDay('2026-10-27T22:46:59Z')).toBe('Tue')
    expect(cardMove(move(-12.5), 'BAL', 'JAX')).toBe('Line moved 12.5 toward JAX since Tue')
    expect(cardMove(move(2), 'BAL', 'JAX')).toBe('Line moved 2 toward BAL since Tue')
  })
  it('keeps small or unknown moves off the card', () => {
    expect(cardMove(move(0.5), 'BAL', 'JAX')).toBeNull()
    expect(cardMove(move(null), 'BAL', 'JAX')).toBeNull()
    expect(cardMove(null, 'BAL', 'JAX')).toBeNull()
  })
  it('describes the path from first to latest', () => {
    const pts = [
      { ts: 'a', spread_home: 2.5, total: 48.75, p_home: 0.56, n_books: 6 },
      { ts: 'b', spread_home: null, total: 45, p_home: null, n_books: 3 },
      { ts: 'c', spread_home: -10, total: 40.5, p_home: 0.19, n_books: 9 },
    ]
    expect(pathSentence(pts, 'BAL', 'JAX')).toBe('Spread BAL −2.5 → JAX −10 · total 48.75 → 40.5')
    expect(pathSentence(pts.slice(0, 1), 'BAL', 'JAX')).toBeNull()
  })
  it('prints half and quarter points', () => {
    expect(fmtPts(2.5)).toBe('2.5')
    expect(fmtPts(48.75)).toBe('48.75')
    expect(windowWords(0.1, 'BAL', 'JAX')).toBe('steady')
    expect(windowWords(-1.5, 'BAL', 'JAX')).toBe('1.5 toward JAX')
  })
})

describe('foldEvents', () => {
  const inj = (team: string, player: string, pos: string, status: string | null, ts = '2026-10-25T15:56:44Z') =>
    ({ ts, kind: 'injury', team, text: `Injury report: ${player} (${pos}, ${team}) listed ${status}`, source_url: null, player, pos, status, was: null })
  it('folds one team’s report changes at one time into one row, Out first', () => {
    const rows = foldEvents([
      inj('PHI', 'Landon Dickerson', 'G', 'Questionable'), inj('PHI', 'DeVonta Smith', 'WR', 'Out'),
      inj('PHI', 'Nolan Smith', 'LB', 'Out'), inj('DAL', 'Dee Winters', 'LB', 'Out'),
      inj('PHI', 'Saquon Barkley', 'RB', null, '2026-10-26T15:00:00Z'),
    ])
    expect(rows.map((r) => r.kind)).toEqual(['report', 'report', 'report'])
    expect(rows[0]).toMatchObject({ team: 'PHI', groups: [{ label: 'Out', players: ['DeVonta Smith (WR)', 'Nolan Smith (LB)'] }, { label: 'Questionable', players: ['Landon Dickerson (G)'] }] })
    expect(rows[1]).toMatchObject({ team: 'DAL', groups: [{ label: 'Out', players: ['Dee Winters (LB)'] }] })
    expect(rows[2]).toMatchObject({ groups: [{ label: 'Off the report', players: ['Saquon Barkley (RB)'] }] })
  })
  it('reads older files from the text, and leaves other events alone', () => {
    const old = { ts: 't', kind: 'injury', team: 'PHI', text: 'Injury report: DeVonta Smith (WR, PHI) now Out (was Questionable)', source_url: null }
    const qb = { ts: 't', kind: 'qb', team: 'PHI', text: 'Depth chart: X listed as PHI’s starting QB', source_url: null }
    const rows = foldEvents([old, qb])
    expect(rows[0]).toMatchObject({ kind: 'report', groups: [{ label: 'Out', players: ['DeVonta Smith (WR)'] }] })
    expect(rows[1]).toMatchObject({ kind: 'one', event: qb })
  })
})
