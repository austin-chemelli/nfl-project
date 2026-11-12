import fs from 'node:fs'
import path from 'node:path'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Game, Lineups } from '../data/contract'
import { Injuries } from '../pages/game/Sections'
import { FormationMap } from './FormationMap'

const spot = (slot: string, player: string, value_pts: number | null, status: string | null = null, p_play: number | null = null) => ({
  slot, player, grp: value_pts === null ? null : 'X', value_pts, status, p_play,
  at_risk: value_pts !== null && p_play !== null ? Math.round(value_pts * (1 - p_play) * 100) / 100 : null,
})

const LINEUPS = Lineups.parse({
  home: {
    chart_ts: '2026-10-24T11:00:00Z',
    reported: true,
    offense_formation: '3WR 1TE',
    defense_formation: 'Base 3-4 D',
    offense: [spot('QB', 'Lamar Jackson', 6.55, 'Out', 0), spot('WR1', 'Zay Flowers', 1.15, 'Questionable', 0.73), spot('C', 'New Center', null)],
    defense: [spot('NT', 'Nose Tackle', null, 'Questionable', 0.7), spot('LCB', 'A Corner', 0.8)],
  },
  away: null,
})

describe('FormationMap', () => {
  it('draws every starter, a status only for listed players, and no number for unvalued spots', () => {
    const { container } = render(<FormationMap lineup={LINEUPS.home!} side="home" />)
    const qb = container.querySelector('[data-slot="QB"]')!
    expect(qb.getAttribute('aria-label')).toBe('QB: Lamar Jackson, worth 6.5 points, Out')
    expect(qb.querySelector('[data-badge="O"]')).not.toBeNull()
    expect(container.querySelector('[data-slot="LCB"] [data-badge]')).toBeNull() // not listed: no status
    expect(container.querySelector('[data-slot="C"]')!.getAttribute('aria-label')).toBe('C: New Center, not valued yet')
    expect(container.querySelector('[data-slot="NT"] [data-badge="Q"]')).not.toBeNull()
    expect(screen.getByText('Base 3-4 D', { exact: false })).toBeInTheDocument()
    // Out: only the ring, no filled core; Questionable: a core
    expect(qb.querySelectorAll('circle').length).toBe(2 + 1) // hit area, ring, badge
    expect(container.querySelector('[data-slot="WR1"]')!.querySelectorAll('circle').length).toBe(2 + 1 + 1)
  })
})

describe('Injuries tab lead', () => {
  const file = path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json')
  const base = JSON.parse(fs.readFileSync(file, 'utf8'))

  it('shows the map and the key players for a side that has them', () => {
    const g = Game.parse({
      ...base,
      lineups: { home: LINEUPS.home, away: null },
      key_players: {
        home: [{ player: 'Lamar Jackson', pos: 'QB', grp: 'QB', status: 'Out', p_play: 0, p_play_n: 900, value_pts: 6.55, at_risk: 6.55, sentence: 'Lamar Jackson is worth about 6.5 points to GB. Out.' }],
        away: [],
      },
    })
    render(<Injuries g={g} />)
    expect(screen.getByTestId('formation-home')).toBeInTheDocument()
    expect(screen.queryByTestId('formation-away')).toBeNull()
    const kp = within(screen.getByTestId('key-players'))
    expect(kp.getByText('Lamar Jackson')).toBeInTheDocument()
    expect(kp.getAllByText('6.5').length).toBe(2) // worth and at risk, as in the JSON
  })

  it('says so when the map comes before any game status, and keeps the lede off a map-less game', () => {
    const early = Game.parse({ ...base, injuries: [], lineups: { home: { ...LINEUPS.home, reported: false }, away: null }, key_players: null })
    render(<Injuries g={early} />)
    expect(screen.getByText(/no report, not a healthy team/)).toBeInTheDocument()
    expect(screen.getAllByText('No official report in our data yet.').length).toBe(2)
  })

  it('shows key players without the map text on a finished game', () => {
    const g = Game.parse({
      ...base,
      lineups: null,
      key_players: { home: [{ player: 'X', pos: 'WR', grp: 'WR', status: 'Out', p_play: 0, p_play_n: 1, value_pts: 1, at_risk: 1, sentence: 'X.' }], away: [] },
    })
    render(<Injuries g={g} />)
    expect(screen.getByTestId('key-players')).toBeInTheDocument()
    expect(screen.queryByText(/sized by what each is worth/)).toBeNull()
  })

  it('keeps the old view when there is no lineup or claim', () => {
    const g = Game.parse({ ...base, lineups: null, key_players: null })
    render(<Injuries g={g} />)
    expect(screen.queryByTestId('formation-home')).toBeNull()
    expect(screen.queryByText(/sized by what each is worth/)).toBeNull()
  })
})
