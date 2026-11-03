import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderRoute } from '../../test/render'

describe('Recap', () => {
  it('shows the week-8 recap above the grid with links to the game', async () => {
    renderRoute('/week/2026/8')
    const region = await screen.findByRole('region', { name: 'Week 8 recap' })
    expect(within(region).getByText(/Best approach:/)).toHaveTextContent('Best approach: The Traditionalist')
    expect(within(region).getByText('0.612')).toBeInTheDocument()
    expect(within(region).getAllByRole('link', { name: 'CAR @ GB' })[0]).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    expect(within(region).getByRole('link', { name: 'GB' })).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    expect(within(region).getByText(/rank here says almost nothing/)).toBeInTheDocument()
  })

  it('renders nothing for a week without a recap', async () => {
    renderRoute('/week/2026/9')
    await screen.findByText(/No slate for 2026 week 9/)
    expect(screen.queryByRole('region', { name: /recap/ })).toBeNull()
  })
})
