import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderRoute } from '../../test/render'

describe('Tracker page', () => {
  it('renders the headline, backtest rows, calibration verdicts and divergence sentences', async () => {
    renderRoute('/tracker')
    expect(await screen.findByText(/^After \d+ games, the Analyst is/)).toBeInTheDocument()
    expect(screen.getByText(/No live locks have been graded yet/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Backtest: how far each line sits from the market/ })).toBeInTheDocument()
    expect(screen.getAllByText('better than the market', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getByText(/The Analyst: (well calibrated|overconfident by \d+ points|underconfident by \d+ points)/)).toBeInTheDocument()
    expect(screen.getByText(/In [\d,]+ games where the Traditionalist disagreed with the market by less than 2.5 points/)).toBeInTheDocument()
    expect(screen.getByText(/Not betting advice; small samples/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /What history would change/ })).toBeInTheDocument()
    expect(screen.getByText(/History would move \d+ of the \w+'s 100 attention points/)).toBeInTheDocument()
  })

  it('lists backtest lines in the numbers table', async () => {
    renderRoute('/tracker')
    const h = await screen.findByRole('heading', { name: /Backtest: how far/ })
    const section = h.closest('section')!
    expect(within(section).getAllByText(/Ensemble/).length).toBeGreaterThan(0)
    expect(within(section).getAllByText(/games and \d+ seasons/, { exact: false }).length).toBeGreaterThan(0)
  })
})
