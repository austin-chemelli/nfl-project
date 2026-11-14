import fs from 'node:fs'
import path from 'node:path'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Game, HealthStarter, TeamHealth } from '../data/contract'
import { Injuries } from '../pages/game/Sections'
import { badge, lastName, outLine, tone } from '../lib/health'
import { DepthField } from './DepthField'

afterEach(cleanup)

const st = (o: Partial<HealthStarter>) =>
  HealthStarter.parse({ slot: 'QB', unit: 'offense', player: 'Q B', grp: 'QB', value_pts: 1, status: null, p_play: 1, missing_pts: 0, ...o })

const rows = [
  st({ slot: 'QB', player: 'Matthew Stafford', key: true }),
  st({ slot: 'WR1', grp: 'WR', player: 'Puka Nacua', key: true, status: 'IR', reserve: true, p_play: 0, since_week: 8, eligible_week: 15, depth: [{ player: 'Tutu Atwell', value_pts: null, status: null }] }),
  st({ slot: 'TE', grp: 'TE', player: 'Tyler Higbee', status: 'Did not practice', doubt: true }),
  st({ slot: 'LCB', unit: 'defense', grp: 'CB', player: 'Jaylen Watson', status: 'Questionable', p_play: 0.75 }),
]

describe('DepthField', () => {
  it('stars key players, empties the ring of a player out and names who steps in', () => {
    render(<DepthField starters={rows} week={11} />)
    const field = screen.getByTestId('depth-field')
    const wr = field.querySelector('svg [data-slot="WR1"]')!
    expect(wr.getAttribute('data-tone')).toBe('out')
    expect(wr.getAttribute('data-key')).toBe('true')
    expect(within(wr as HTMLElement).getByText('→ Atwell')).toBeInTheDocument()
    expect(wr.querySelector('[data-badge="IR"]')).not.toBeNull()
    expect(field.querySelector('svg [data-slot="TE"] [data-badge="?"]')).not.toBeNull()
    expect(field.querySelector('svg [data-slot="LCB"]')!.getAttribute('data-tone')).toBe('iffy')
    // no player values anywhere on the field
    expect(field.textContent).not.toMatch(/pts/)
  })

  it('reads as room cards on a phone, with the return window', () => {
    render(<DepthField starters={rows} week={11} />)
    const room = screen.getByTestId('depth-field').querySelector('[data-room="WR"]') as HTMLElement
    expect(within(room).getByText(/IR since Wk 8 · eligible Wk 15 → Tutu Atwell/)).toBeInTheDocument()
  })

  it('names tones, badges and counts', () => {
    expect([tone(rows[0]), tone(rows[1]), tone(rows[2]), tone(rows[3])]).toEqual(['in', 'out', 'doubt', 'iffy'])
    expect(rows.map(badge)).toEqual([null, 'IR', '?', 'Q'])
    expect(lastName('Marvin Harrison Jr.')).toBe('Harrison Jr.')
    expect(outLine(5, 3)).toBe('5 starters out, 3 of them key')
    expect(outLine(1, 1)).toBe('1 starter out, a key player')
    expect(outLine(0, 0)).toBe('no starters out')
  })
})

describe('Injuries tab with team health', () => {
  const base = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json'), 'utf8'))
  const was = TeamHealth.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../test/fixtures/site/team_health_WAS.json'), 'utf8'))).now

  it('draws the full-strength field for a side with health and keeps the old map for the other', () => {
    const g = Game.parse({ ...base, health: { home: was, away: null } })
    render(<Injuries g={g} />)
    expect(screen.getByTestId('health-header').textContent).toBe(`${g.home} 84% of full strength (4 starters out, 3 of them key)`)
    const field = screen.getByTestId('depth-field-home')
    expect(field.querySelector('svg [data-slot="LT"] [data-badge="IR"]')).not.toBeNull()
    expect(screen.queryByTestId('depth-field-away')).toBeNull()
  })
})
