import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'

describe('Game page', () => {
  it('renders header, contributions, edges, tendencies and the narrative for CAR @ GB', async () => {
    renderRoute('/game/2026_08_CAR_GB')
    expect(await screen.findByText(/Lambeau Field/)).toBeInTheDocument()
    expect(screen.getAllByText(/Bryce Young/).length).toBeGreaterThan(0)
    // approaches vs market
    expect(screen.getByRole('img', { name: /Home win chance for GB by model/ })).toBeInTheDocument()
    // why: home field +6.2 pts for the analyst, shown in the chart title and group list
    expect(screen.getByText(/Inside each group/)).toBeInTheDocument()
    expect(screen.getAllByText(/toward GB/).length).toBeGreaterThan(0)
    // edges as percentile sentences
    expect(screen.getByText(/edge is in the 88th percentile of matchups/)).toBeInTheDocument()
    // tendencies
    expect(screen.getByText('CAR offense vs GB defense')).toBeInTheDocument()
    expect(screen.getByText('Defensive habits')).toBeInTheDocument()
    // narrative
    expect(screen.getByText(/What people are saying about the matchup/)).toBeInTheDocument()
    expect(screen.getByText(/Carolina's run defense is among the league's worst/)).toBeInTheDocument()
    expect(screen.getByText(/claude-code\/sonnet-5.5/)).toBeInTheDocument()
    expect(screen.getByText(/Claims and sources/)).toBeInTheDocument()
  })

  it('switches approach and situation', async () => {
    renderRoute('/game/2026_08_CAR_GB')
    await screen.findByText(/Lambeau Field/)
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Approach' })).getByRole('radio', { name: 'Analyst' }))
    expect(screen.getByText(/Analyst says: GB win chance 71.2%/)).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Situation' })).getByRole('radio', { name: 'Third down' }))
    expect(screen.getByRole('radio', { name: 'Third down' })).toHaveAttribute('aria-checked', 'true')
  })

  it('shows "no narrative" for a game without one', async () => {
    renderRoute('/game/2026_08_ARI_DAL')
    expect(await screen.findByText(/No narrative research for this game yet/)).toBeInTheDocument()
  })

  it('is friendly when the game file is missing', async () => {
    renderRoute('/game/2026_08_AAA_BBB')
    expect(await screen.findByText(/No detail file for this game yet/)).toBeInTheDocument()
  })
})
