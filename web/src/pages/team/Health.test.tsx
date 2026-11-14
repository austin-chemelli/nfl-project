import fs from 'node:fs'
import path from 'node:path'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import { TeamHealth, type HealthStarter, type TeamFile } from '../../data/contract'
import { healthTile } from './summary'
import { Health } from './Health'
import { whenBack } from '../../lib/health'

afterEach(cleanup)

const fixture = path.resolve(import.meta.dirname, '../../test/fixtures/site/team_health_WAS.json')
const health = TeamHealth.parse(JSON.parse(fs.readFileSync(fixture, 'utf8')))
const file = { health } as unknown as TeamFile
const ui = (f: TeamFile) => render(<MemoryRouter><Health file={f} /></MemoryRouter>)

describe('Health tab', () => {
  it('leads with the share of full strength, then groups, who is missing and the chart', () => {
    ui(file)
    expect(screen.getByText(/At 84% of full strength going into Week 11: 4 starters out, 3 of them key/)).toBeInTheDocument()
    const groups = within(screen.getByTestId('health-rooms'))
    expect(groups.getByText(/missing Terry McLaurin ★ \(1 of 3\)/)).toBeInTheDocument()
    expect(screen.getByTestId('health-rooms').textContent).not.toMatch(/pts/)
    const depth = within(screen.getByTestId('health-depth'))
    expect(depth.getByText(/IR since camp · no return window/)).toBeInTheDocument()
    expect(depth.getByText(/IR since Wk 8 · eligible Wk 12/)).toBeInTheDocument()
    expect(screen.getByTestId('health-depth').querySelector('[data-view="field"] [data-slot="WR1"]')!.getAttribute('data-tone')).toBe('out')
    expect(screen.getByTestId('health-depth').querySelector('[data-slot="QB"]')).not.toBeNull()
    expect(screen.getByTestId('health-chart').querySelectorAll('[data-kind="outlook"]').length).toBe(health.outlook.length)
  })

  it('grades each position room and says which falls furthest with the injuries', () => {
    ui(file)
    expect(screen.getByText(/of them key\. Biggest drop: receivers, #1 at full strength to about #12 now\./)).toBeInTheDocument()
    expect(screen.queryByTestId('health-groups')).toBeNull()
    expect(screen.getByTestId('health-rooms').querySelector('[data-room="WR"]')!.textContent).toContain('~#12#1')
  })

  it('notes when the week has no game statuses yet', () => {
    ui(file)
    expect(screen.getByText(/No game statuses yet this week/)).toBeInTheDocument()
  })

  it('renders nothing without health, and the tile reads the share', () => {
    const { container } = ui({ health: null } as unknown as TeamFile)
    expect(container.innerHTML).toBe('')
    expect(healthTile(file)).toMatchObject({ label: 'Health', value: '84%', sub: 'of full strength, 4 starters out, 3 of them key', tab: 'health' })
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
    const now = { ...health.now, reported: false,
      starters: health.now.starters.map((s) => (s.grp === 'CB' ? { ...s, status: 'Did not practice', doubt: true } : s)) }
    const { container } = ui({ health: { ...health, now } } as unknown as TeamFile)
    expect(screen.getByTestId('health-doubt').textContent).toMatch(/In doubt from practice: .+ \(marked under their rooms/)
    expect(container.querySelector('[data-doubt]')).not.toBeNull()
    expect(screen.getByText(/At 84% of full strength/)).toBeInTheDocument()
  })

  it('says when a player can be back', () => {
    const s = { status: 'IR', reserve: true, since_week: 9, eligible_week: 13 } as HealthStarter
    expect(whenBack(s, 11)).toBe('IR since Wk 9 · eligible Wk 13')
    expect(whenBack({ ...s, eligible_week: 10 }, 11)).toBe('IR since Wk 9 · eligible now')
    expect(whenBack({ ...s, reserve: false, status: 'Questionable' }, 11)).toBe('Questionable')
  })
})
