import fs from 'node:fs'
import path from 'node:path'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import { TeamHealth, type HealthStarter, type TeamFile } from '../../data/contract'
import { healthTile } from './summary'
import { Health, whenBack } from './Health'

afterEach(cleanup)

const fixture = path.resolve(import.meta.dirname, '../../test/fixtures/site/team_health_WAS.json')
const health = TeamHealth.parse(JSON.parse(fs.readFileSync(fixture, 'utf8')))
const file = { health } as unknown as TeamFile
const ui = (f: TeamFile) => render(<MemoryRouter><Health file={f} /></MemoryRouter>)

describe('Health tab', () => {
  it('leads with the share of full strength, then groups, who is missing and the chart', () => {
    ui(file)
    expect(screen.getByText(/At 80% of full strength going into Week 11/)).toBeInTheDocument()
    const groups = within(screen.getByTestId('health-groups'))
    expect(groups.getByText(/missing Terry McLaurin/)).toBeInTheDocument()
    const depth = within(screen.getByTestId('health-depth'))
    expect(depth.getByText(/IR since camp · no return window/)).toBeInTheDocument()
    expect(depth.getByText(/IR since Wk 8 · eligible Wk 12/)).toBeInTheDocument()
    expect(screen.getByTestId('health-depth').querySelector('[data-slot="QB"]')).not.toBeNull()
    expect(screen.getByTestId('health-chart').querySelectorAll('[data-kind="outlook"]').length).toBe(health.outlook.length)
  })

  it('notes when the week has no game statuses yet', () => {
    ui(file)
    expect(screen.getByText(/No game statuses yet this week/)).toBeInTheDocument()
  })

  it('renders nothing without health, and the tile reads the share', () => {
    const { container } = ui({ health: null } as unknown as TeamFile)
    expect(container.innerHTML).toBe('')
    expect(healthTile(file)).toMatchObject({ label: 'Health', value: '80%', tab: 'health' })
    expect(healthTile(undefined)).toBeNull()
  })

  it('shows the claims sentences only once the report is in', () => {
    const kp = { player: 'Sam Star', pos: 'WR', grp: 'WR', status: 'Out', p_play: 0, p_play_n: 1, value_pts: 1, at_risk: 1, sentence: 'Sam Star is Out.' }
    ui({ health, availability: { week: 11, players: [], listed: [kp], reported: true, value_at_risk: 1 } } as unknown as TeamFile)
    expect(screen.getByTestId('health-claims').textContent).toBe('Sam Star is Out.')
    cleanup()
    ui({ health, availability: { week: 11, players: [], listed: [kp], reported: false, value_at_risk: null } } as unknown as TeamFile)
    expect(screen.queryByTestId('health-claims')).toBeNull()
  })

  it('stripes and names practice doubts before Friday, without counting them', () => {
    const now = { ...health.now, reported: false, doubt_pts: 0.9,
      groups: health.now.groups.map((g) => (g.grp === 'CB' ? { ...g, doubt_pts: 0.9 } : g)),
      starters: health.now.starters.map((s) => (s.grp === 'CB' ? { ...s, status: 'Did not practice', doubt: true } : s)) }
    const { container } = ui({ health: { ...health, now } } as unknown as TeamFile)
    expect(screen.getByTestId('health-doubt').textContent).toMatch(/In doubt from practice: .+ \(0\.9 pts/)
    expect(container.querySelector('[data-doubt]')).not.toBeNull()
    expect(screen.getByText(/At 80% of full strength/)).toBeInTheDocument()
  })

  it('says when a player can be back', () => {
    const s = { status: 'IR', reserve: true, since_week: 9, eligible_week: 13 } as HealthStarter
    expect(whenBack(s, 11)).toBe('IR since Wk 9 · eligible Wk 13')
    expect(whenBack({ ...s, eligible_week: 10 }, 11)).toBe('IR since Wk 9 · eligible now')
    expect(whenBack({ ...s, reserve: false, status: 'Questionable' }, 11)).toBe('Questionable')
  })
})
