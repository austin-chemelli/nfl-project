import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { renderRoute } from '../../test/render'

/** The fixtures without one site file. */
function without(file: string): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'team-'))
  fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
  fs.rmSync(path.join(root, 'site', file))
  return root
}

describe('team page', () => {
  it('opens on the overview with the tiles and all four tabs', async () => {
    renderRoute('/team/CAR')
    expect(await screen.findByRole('heading', { name: /Carolina Panthers/ })).toBeInTheDocument()
    expect(await screen.findByText('Calls the offense')).toBeInTheDocument()
    for (const name of ['Overview', 'Staff', 'Tendencies', 'Games']) expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
  })

  it('accepts a lower-case code and an old franchise code', async () => {
    renderRoute('/team/car')
    expect(await screen.findByRole('heading', { name: /Carolina Panthers/ })).toBeInTheDocument()
  })

  it('sends an old code to the franchise', async () => {
    renderRoute('/team/sd')
    expect(await screen.findByRole('heading', { name: /Los Angeles Chargers/ })).toBeInTheDocument()
  })

  it('answers an unknown code as a missing page', async () => {
    renderRoute('/team/xyz')
    expect(await screen.findByRole('heading', { name: 'Not found' })).toBeInTheDocument()
  })

  it('says a team with no file yet will fill in, and keeps the rest', async () => {
    renderRoute('/team/KC?tab=staff')
    await waitFor(() => expect(screen.getByText('Staff details appear after the next data update.')).toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
  })

  it('draws the tendencies: so far, then what to expect', async () => {
    renderRoute('/team/LAC?tab=tendencies')
    expect(await screen.findByRole('heading', { name: 'Offense this season' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Offense: what to watch for' })).toBeInTheDocument()
    expect(screen.getAllByTestId('this-season').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('caller-past').length).toBeGreaterThan(0)
    expect(screen.getByText(/until .* is in/)).toBeInTheDocument()
  })

  it('sets the team color wherever a tab uses it', async () => {
    const { container } = renderRoute('/team/CAR')
    await screen.findByText('Best and worst')
    expect(container.querySelector('[role="tabpanel"] [data-matchup]')).not.toBeNull()
  })

  it('doesn\'t predict what the weekly numbers already show', async () => {
    renderRoute('/team/LAC?tab=tendencies')
    await screen.findByRole('heading', { name: 'Offense: what to watch for' })
    expect(screen.queryByText('Shotgun', { exact: true })).not.toBeInTheDocument()
  })

  it('keeps the league sections, the picker and the tabs without teams.json', async () => {
    renderRoute('/team/CAR', without('teams.json'))
    expect(await screen.findByText('Where they stand')).toBeInTheDocument()
    expect(screen.queryByText('Best and worst')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('CAR')
  })

  it('keeps the tab when it redirects a code', async () => {
    renderRoute('/team/car?tab=staff')
    expect(await screen.findByRole('tab', { name: 'Staff' })).toHaveAttribute('aria-selected', 'true')
  })

  it('is in the nav, after League', async () => {
    renderRoute('/team')
    const nav = await screen.findByRole('navigation')
    const labels = within(nav).getAllByRole('link').map((a) => a.textContent)
    expect(labels.indexOf('Teams')).toBe(labels.indexOf('League') + 1)
  })

  it('is linked from the game header without nesting links', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB')
    expect((await screen.findAllByRole('link', { name: 'CAR' }))[0]).toHaveAttribute('href', '/team/CAR')
    expect(container.querySelector('a a')).toBeNull()
  })

  it('is linked from the playoff odds without nesting links', async () => {
    const { container } = renderRoute('/league')
    expect((await screen.findAllByRole('link', { name: 'KC' }))[0]).toHaveAttribute('href', '/team/KC')
    expect(container.querySelector('a a')).toBeNull()
  })

  it('lists the teams by division', async () => {
    renderRoute('/team')
    expect(await screen.findByRole('link', { name: /Carolina Panthers/ })).toHaveAttribute('href', '/team/CAR')
  })
})
