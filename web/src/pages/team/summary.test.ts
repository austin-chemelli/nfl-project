import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile, TeamFile, TeamsFile } from '../../data/contract'
import { callerTile, changeTile, nextGameTile, playoffTile } from './summary'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const read = (f: string) => JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8'))
const league = LeagueFile.parse(read('league.json'))
const teams = TeamsFile.parse(read('teams.json'))
const car = TeamFile.parse(read('team/CAR.json'))

describe('team tiles', () => {
  it('states the playoff chance and drops without the file or an entry', () => {
    expect(playoffTile(league, 'CAR')?.label).toBe('Playoff chance')
    expect(playoffTile(undefined, 'CAR')).toBeNull()
    expect(playoffTile(league, 'XXX')).toBeNull()
  })
  it('names a confirmed caller with his situation', () => {
    const t = callerTile(car.units.off.caller, 'off')
    expect(t).toMatchObject({ label: 'Calls the offense', value: 'Brad Idzik', sub: 'First NFL year calling, promoted' })
  })
  it('a mid-season change beats the situation', () => {
    expect(callerTile(car.units.off.caller, 'off', 5)?.sub).toBe('Took over in Week 5')
  })
  it('an unconfirmed unit never reads as calling', () => {
    const t = callerTile({ ...car.units.off.caller!, confirmed: false }, 'off')
    expect(t).toMatchObject({ label: 'Runs the offense', sub: 'Play-caller not confirmed' })
    expect(callerTile(null, 'def')).toBeNull()
  })
  it('keeps every tile sub-line to six words', () => {
    const subs = ['same_caller', 'same_caller_new_qb', 'took_over', 'moved_team', 'promoted_first_time', 'outside_first_time']
      .map((situation) => callerTile({ ...car.units.off.caller!, situation }, 'off')?.sub ?? '')
    for (const s of subs) expect(s.split(' ').length).toBeLessThanOrEqual(6)
  })
  it('names the biggest move from last season, and drops when nothing moved much', () => {
    const lac = TeamFile.parse(read('team/LAC.json'))
    const t = changeTile(lac)
    expect(t?.label).toBe('Biggest change')
    expect(t?.sub).toMatch(/^\d+(st|nd|rd|th) last year, \d+(st|nd|rd|th) now$/)
    const calm = { ...car, units: { off: { ...car.units.off, live: [] }, def: { ...car.units.def, live: [] } } }
    expect(changeTile(calm)).toBeNull()
    expect(changeTile(undefined)).toBeNull()
  })
  it('gives the next game, or nothing after the last one', () => {
    const row = teams.teams.CAR
    expect(nextGameTile(row)?.tab).toBe('games')
    expect(nextGameTile({ ...row, next_game_id: null })).toBeNull()
  })
})
