import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'

describe('Slate page', () => {
  it('renders the week-8 games with picks, line and market', async () => {
    renderRoute('/')
    expect((await screen.findAllByText('CAR @ GB')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('ARI').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /Week 8/ })).toBeInTheDocument()
    // Fixture: market GB 64%, line GB −3.5; the ensemble's 71% in the file must not reach the strip
    const card = screen.getByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(card).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    expect(within(card).getByText(/market GB 64%/)).toBeInTheDocument()
    expect(within(card).getByText(/GB −3.5/)).toBeInTheDocument()
    expect(within(card).getByRole('img')).toHaveAccessibleName(/market 64%.*Student \d+%/)
    expect(within(card).getByRole('img').getAttribute('aria-label')).not.toMatch(/Ensemble/)
    expect(screen.queryByRole('heading', { name: /Where they disagree most/ })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: /Kickoff/ })).toBeNull()
  })

  it('renders one card per game with every card a link', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.getAllByRole('link', { name: /^[A-Z]+\s*@\s*[A-Z]+.*(ET|Final)/ })).toHaveLength(14)
  })

  it('says the status once above the grid, not on every card', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    // fixture: 13 games not locked, 1 preview; the usual status is said once, the odd one is marked on its card
    expect(screen.getByText(/on most games/)).toBeInTheDocument()
    expect(within(screen.getByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })).queryByText('Not locked')).toBeNull()
    expect(screen.getAllByRole('link', { name: /^[A-Z]+\s*@\s*[A-Z]+.*(ET|Final)/ }).filter((a) => within(a).queryByText('Preview'))).toHaveLength(1)
  })

  it('sorts by ?sort= and the control updates the URL order', async () => {
    renderRoute('/?sort=disagreement')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.getByRole('radio', { name: 'Disagreement' })).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(screen.getByRole('radio', { name: 'Kickoff' }))
    expect(screen.getByRole('radio', { name: 'Kickoff' })).toHaveAttribute('aria-checked', 'true')
  })

  it('shows the table with ?view=table and a link back to cards', async () => {
    renderRoute('/?view=table')
    expect(await screen.findByRole('columnheader', { name: /Kickoff/ })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'CAR @ GB' })[0]).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    await userEvent.click(screen.getByRole('link', { name: 'Show as cards' }))
    expect(await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /Kickoff/ })).toBeNull()
  })

  it('puts the legend in the fine print', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.getAllByText('Fine print')).toHaveLength(1)
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
