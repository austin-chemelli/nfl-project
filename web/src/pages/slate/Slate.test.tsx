import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'

describe('Slate page', () => {
  it('renders the week-8 games with picks, line and market', async () => {
    renderRoute('/')
    expect((await screen.findAllByText('CAR @ GB')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('ARI @ DAL').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /Week 8/ })).toBeInTheDocument()
    // Fixture: ensemble GB 71%, market GB 64%, line GB −3.5
    const row = screen.getAllByText('CAR @ GB')[0].closest('tr') as HTMLElement
    expect(within(row).getAllByText('71%').length).toBeGreaterThan(0)
    expect(within(row).getByText('64%')).toBeInTheDocument()
    expect(within(row).getByText('GB −3.5')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Where they disagree most/ })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'CAR @ GB' })[0]).toHaveAttribute('href', '/game/2026_08_CAR_GB')
  })

  it('opens an explicit week and shows a friendly message for a missing slate', async () => {
    renderRoute('/week/2026/9')
    expect(await screen.findByText(/No slate for 2026 week 9/)).toBeInTheDocument()
  })

  it('week picker navigates', async () => {
    renderRoute('/')
    await screen.findAllByText('CAR @ GB')
    await userEvent.click(screen.getByRole('button', { name: 'Next week' }))
    expect(await screen.findByText(/No slate for 2026 week 9/)).toBeInTheDocument()
  })
})
