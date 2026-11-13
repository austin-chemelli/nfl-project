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
    const missing = within(screen.getByTestId('health-missing'))
    expect(missing.getByText('IR since camp · no return window')).toBeInTheDocument()
    expect(missing.getByText('IR since Wk 8 · eligible Wk 12')).toBeInTheDocument()
    expect(screen.getByTestId('health-chart').querySelectorAll('[data-kind="outlook"]').length).toBe(health.outlook.length)
  })

  it('notes when the week has no game statuses yet', () => {
    ui(file)
    expect(screen.getByText(/no game statuses yet/)).toBeInTheDocument()
  })

  it('renders nothing without health, and the tile reads the share', () => {
    const { container } = ui({ health: null } as unknown as TeamFile)
    expect(container.innerHTML).toBe('')
    expect(healthTile(file)).toMatchObject({ label: 'Health', value: '80%', tab: 'health' })
    expect(healthTile(undefined)).toBeNull()
  })

  it('says when a player can be back', () => {
    const s = { status: 'IR', reserve: true, since_week: 9, eligible_week: 13 } as HealthStarter
    expect(whenBack(s, 11)).toBe('IR since Wk 9 · eligible Wk 13')
    expect(whenBack({ ...s, eligible_week: 10 }, 11)).toBe('IR since Wk 9 · eligible now')
    expect(whenBack({ ...s, reserve: false, status: 'Questionable' }, 11)).toBe('Questionable')
  })
})
