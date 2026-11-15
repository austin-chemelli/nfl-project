import { describe, expect, it } from 'vitest'
import { TeamsFile, type TeamFeature } from '../../data/contract'
import raw from '../../test/fixtures/site/teams.json'
import { withByes, withStandings, buildPoints, colorMode, divisionsOf, featureById, fmtValue, ordinal, quadrantsFor, rankText, resolveAxes, templateQuadrants, toneFor } from './helpers'

const file = TeamsFile.parse(raw)
const f = (id: string) => featureById(file, id)!

describe('resolveAxes', () => {
  it('falls back to preset 1 for an unknown or missing id', () => {
    const d = resolveAxes(file, null, null)!
    expect([d.x.id, d.y.id]).toEqual(['strength.epa_off', 'strength.epa_def'])
    const u = resolveAxes(file, 'nope.nothing', 'strength.luck')!
    expect([u.x.id, u.y.id]).toEqual(['strength.epa_off', 'strength.epa_def'])
  })
  it('keeps a valid pair', () => {
    const r = resolveAxes(file, 'strength.luck', 'strength.sos')!
    expect([r.x.id, r.y.id]).toEqual(['strength.luck', 'strength.sos'])
  })
  it('falls back when a selected axis has no data in the file', () => {
    const bare = structuredClone(file)
    for (const t of Object.values(bare.teams)) delete t.values['strength.luck']
    expect(resolveAxes(bare, 'strength.luck', 'strength.sos')!.x.id).toBe('strength.epa_off')
  })
})

describe('captions', () => {
  it('uses the preset captions for a preset pair', () => {
    expect(quadrantsFor(f('strength.epa_off'), f('strength.epa_def'))[1]).toBe('Good on both sides')
  })
  it('templates a directional pair: better to the right and up', () => {
    const q = templateQuadrants(f('strength.elo_pre'), f('strength.epa_def'))
    expect(q[0]).toBe('Worse Elo rating, better defense EPA')
    expect(q[1]).toBe('Better Elo rating, better defense EPA')
    expect(q[2]).toBe('Worse Elo rating, worse defense EPA')
    expect(q[3]).toBe('Better Elo rating, worse defense EPA')
  })
  it('templates a neutral pair as higher and lower, and never flips', () => {
    const q = templateQuadrants(f('strength.luck'), f('strength.sos'))
    expect(q).toEqual([
      'Lower luck, higher schedule strength',
      'Higher luck, higher schedule strength',
      'Lower luck, lower schedule strength',
      'Higher luck, lower schedule strength',
    ])
    expect(f('strength.luck').better).toBeNull()
  })
  it('mixes a neutral axis with a directional one', () => {
    expect(templateQuadrants(f('strength.luck'), f('strength.elo_pre'))[0]).toBe('Lower luck, better Elo rating')
  })
})

describe('points and tones', () => {
  it('builds 32 points in alphabetical order with the conference tone', () => {
    const { points, missing } = buildPoints(file, f('strength.epa_off'), f('strength.epa_def'), 'conference', null)
    expect(points).toHaveLength(32)
    expect(missing).toEqual([])
    expect(points.map((p) => p.key)).toEqual([...points.map((p) => p.key)].sort())
    const kc = points.find((p) => p.key === 'KC')!
    expect(kc.tone).toBe('conf-afc')
    expect(points.find((p) => p.key === 'GB')!.tone).toBe('conf-nfc')
  })
  it('names the teams without a value and leaves them out', () => {
    const t = structuredClone(file)
    delete t.teams.KC.values['strength.luck']
    const { points, missing } = buildPoints(t, f('strength.luck'), f('strength.sos'), 'none', null)
    expect(missing).toEqual(['KC'])
    expect(points).toHaveLength(31)
    expect(points[0].tone).toBeUndefined()
  })
  it('highlights one division and mutes the rest', () => {
    const { points } = buildPoints(file, f('strength.epa_off'), f('strength.epa_def'), 'division', 'AFC West')
    expect(points.filter((p) => p.tone === 'strong').map((p) => p.key).sort()).toEqual(['DEN', 'KC', 'LAC', 'LV'])
    expect(points.filter((p) => p.tone === 'muted')).toHaveLength(28)
    expect(toneFor(file.teams.KC, 'division', null)).toBeUndefined()
    expect(points.find((p) => p.key === 'KC')!.dot).toBeDefined() // the division keeps its team colors
    expect(points.find((p) => p.key === 'GB')!.dot).toBeUndefined() // the rest go gray
  })
  it('gives every team its own dot by default, and only there', () => {
    const on = (mode: 'team' | 'conference' | 'none') => buildPoints(file, f('strength.epa_off'), f('strength.epa_def'), mode, null).points
    expect(on('team').every((p) => p.dot && p.tone === undefined)).toBe(true)
    expect(on('conference').some((p) => p.dot)).toBe(false)
    expect(on('none').some((p) => p.dot)).toBe(false)
  })
  it('lists eight divisions', () => expect(divisionsOf(file)).toHaveLength(8))
  it('parses the color mode', () => {
    expect([colorMode(null), colorMode('conference'), colorMode('division'), colorMode('none'), colorMode('x')]).toEqual(['team', 'conference', 'division', 'none', 'team'])
  })
})

describe('text', () => {
  it('writes ordinals', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 32].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '32nd'])
  })
  it('writes a rank against the field size', () => {
    expect(rankText(file.teams.KC, f('strength.epa_off'))).toBe('5th of 32')
  })
})

describe('fmtValue', () => {
  const m = (id: string, unit: string) => ({ id, unit }) as TeamFeature
  it('keeps a decimal on rates, so close ranks can be told apart', () => expect(fmtValue(0.0634, m('strength.sack_rate_off', 'pct'))).toBe('6.3%'))
  it('reads a gap in a rate as a percent, because "pts" means win chance elsewhere', () => {
    expect(fmtValue(0.168, m('strength.luck', 'prob_diff'))).toBe('+16.8%')
    expect(fmtValue(6.8, m('decisions.pass_rate_oe', 'pp'))).toBe('+6.8%')
  })
  it('signs a gap to the league average, with no negative zero', () => {
    expect(fmtValue(0.13, m('scheme.off_11_rate_prior', 'pct'))).toBe('+13.0%')
    expect(fmtValue(-0.0001, m('scheme.def_pressure_rate_prior', 'pct'))).toBe('0.0%')
    expect(fmtValue(0.11, m('scheme.off_time_to_throw_prior', 'seconds'))).toBe('+0.11 s')
  })
  it('shows a dash for no value', () => expect(fmtValue(undefined, m('strength.luck', 'prob_diff'))).toBe('–'))
})

describe('resolveAxes', () => {
  it('refuses the same measure on both axes', () => {
    const a = resolveAxes(file, 'strength.epa_off', 'strength.epa_off')
    expect([a?.x.id, a?.y.id]).toEqual(['strength.epa_off', 'strength.epa_def'])
  })
})

describe('fmtValue signed counts', () => {
  it('prints turnover margin and streak with a sign and a true minus', () => {
    expect(fmtValue(-0.2, f('decisions.turnover_margin_pg'))).toBe('−0.2')
    expect(fmtValue(0.3, f('decisions.turnover_margin_pg'))).toBe('+0.3')
    expect(fmtValue(0, f('decisions.turnover_margin_pg'))).toBe('0')
    expect(fmtValue(-3, { ...f('decisions.turnover_margin_pg'), id: 'form.streak' })).toBe('−3')
    expect(fmtValue(4, { ...f('decisions.turnover_margin_pg'), id: 'form.streak' })).toBe('+4')
  })
})

describe('withStandings', () => {
  const row = file.teams.CAR
  const st = { team: 'CAR', w: 9, l: 0, t: 0 }
  const league = { teams: [st], played: [{ week: 9, home: 'CAR', away: 'DEN', home_score: 24, away_score: 20 }] } as never
  it('takes the record from the standings and fills scores teams.json has not caught up on', () => {
    const t = withStandings(row, 'CAR', league)
    expect([t.wins, t.losses, t.ties]).toEqual([9, 0, 0])
    const g = t.games.find((x) => x.id === '2026_09_DEN_CAR')!
    expect([g.pf, g.pa]).toEqual([24, 20])
    // that game was "next"; the next is now the first unscored one
    expect(t.next_game_id).toBe('2026_10_CAR_NO')
    expect(t.through_week).toBe(row.through_week) // the values' week stays as built
  })
  it('leaves the row alone without a league file or a standings row', () => {
    expect(withStandings(row, 'CAR', undefined)).toBe(row)
    expect(withStandings(row, 'CAR', { teams: [], played: [] } as never)).toBe(row)
  })
})

describe('withByes', () => {
  it('adds a row for each missing week between the first and last game', () => {
    const out = withByes([1, 2, 3, 4, 6, 7].map((week) => ({ week })))
    expect(out.map((g) => ('bye' in g ? `bye ${g.week}` : g.week))).toEqual([1, 2, 3, 4, 'bye 5', 6, 7])
    expect(withByes([])).toEqual([])
  })
})
