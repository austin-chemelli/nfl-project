import { cleanup, render, screen, within } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import { MemoryRouter } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { LeagueFile, TeamFile, TeamsFile } from '../../data/contract'
import { Games } from './Games'

// after Week 8's last kickoff, so only Week 10's TB at CAR is still to come
const FIXTURE_NOW = new Date('2026-11-03T12:00:00Z')
beforeAll(() => { vi.useFakeTimers({ toFake: ['Date'], now: FIXTURE_NOW }) })
afterAll(() => { vi.useRealTimers() })
afterEach(cleanup)

const SITE = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const read = (f: string) => JSON.parse(fs.readFileSync(path.join(SITE, f), 'utf8'))
const teams = TeamsFile.parse(read('teams.json'))
const league = LeagueFile.parse(read('league.json'))
const car = TeamFile.parse(read('team/CAR.json'))

const show = (p: { league?: LeagueFile; file?: TeamFile }) =>
  render(
    <MemoryRouter>
      <Games code="CAR" teams={teams} {...p} />
    </MemoryRouter>,
  )

describe('Games tab', () => {
  it('lists every game with a link and marks the next one', () => {
    show({ league, file: car })
    const list = within(screen.getByRole('region', { name: 'Every game' }))
    expect(list.getAllByRole('link')).toHaveLength(17)
    expect(list.getByRole('link', { name: /Wk 1 vs CHI L 37–59/ })).toHaveAttribute('href', '/game/2026_01_CHI_CAR')
    expect(list.getByRole('link', { name: /Wk 9 vs DEN next/ })).toHaveAttribute('href', '/game/2026_09_DEN_CAR')
  })

  it('shows the staff change under the Week 9 row', () => {
    show({ league, file: car })
    const row = screen.getByRole('link', { name: /Wk 9 vs DEN/ }).closest('li')!
    expect(within(row).getByText('Todd Wash took over the defense')).toBeInTheDocument()
  })

  it('lists the games that matter with the swing', () => {
    show({ league, file: car })
    const sec = within(screen.getByRole('region', { name: 'Games that matter' }))
    expect(sec.getByRole('link', { name: 'TB @ CAR' })).toHaveAttribute('href', '/game/2026_10_TB_CAR')
    expect(sec.getByText(/^CAR \d+% → \d+% with a win$/)).toBeInTheDocument()
  })

  it('drops Games that matter without a league file and keeps the list', () => {
    show({ file: car })
    expect(screen.queryByText('Games that matter')).toBeNull()
    expect(screen.getAllByRole('link')).toHaveLength(17)
  })

  it('shows no notes without a team file', () => {
    show({ league })
    const row = screen.getByRole('link', { name: /Wk 9 vs DEN/ }).closest('li')!
    expect(within(row).queryByText(/took over/)).toBeNull()
    expect(screen.queryByText(/started$/)).toBeNull()
  })
})
