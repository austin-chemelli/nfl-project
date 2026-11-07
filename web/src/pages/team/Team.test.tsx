import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'

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
    expect(await screen.findByRole('heading', { name: 'Offense so far' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Offense: what to expect' })).toBeInTheDocument()
    expect(screen.getAllByTestId('so-far-dot').length).toBeGreaterThan(0)
    expect(screen.getByText(/isn't in yet/)).toBeInTheDocument()
  })

  it('sets the team color wherever a tab uses it', async () => {
    const { container } = renderRoute('/team/CAR')
    await screen.findByText('Best and worst')
    expect(container.querySelector('[role="tabpanel"] [data-matchup]')).not.toBeNull()
  })

  it('doesn\'t predict what the weekly numbers already show', async () => {
    renderRoute('/team/LAC?tab=tendencies')
    await screen.findByRole('heading', { name: 'Offense: what to expect' })
    expect(screen.queryByText('Shotgun', { exact: true })).not.toBeInTheDocument()
  })

  it('lists the teams by division', async () => {
    renderRoute('/team')
    expect(await screen.findByRole('link', { name: /Carolina Panthers/ })).toHaveAttribute('href', '/team/CAR')
  })
})
