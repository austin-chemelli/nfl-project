import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'

describe('Tracker page', () => {
  it('shows the five-tile strip and the season tab by default', async () => {
    renderRoute('/tracker')
    const strip = await screen.findByRole('group', { name: 'Tracker summary' })
    expect(within(strip).getAllByRole('button')).toHaveLength(5)
    expect(await screen.findByText(/^After \d+ games, the Analyst is/)).toBeInTheDocument()
    expect(screen.getByText(/No live locks have been graded yet/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Log loss by season/ })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Backtest: how far/ })).not.toBeInTheDocument()
  })

  it('a strip tile opens the tab that explains it', async () => {
    renderRoute('/tracker')
    const strip = await screen.findByRole('group', { name: 'Tracker summary' })
    await userEvent.click(within(strip).getByRole('button', { name: /Paper bets/ }))
    expect(await screen.findByText(/Not betting advice; small samples/)).toBeInTheDocument()
  })

  it('backtest tab: backtest rows and the persona-vs-history view', async () => {
    renderRoute('/tracker?tab=backtest')
    const h = await screen.findByRole('heading', { name: /Backtest: how far/ })
    const section = h.closest('section')!
    expect(within(section).getAllByText(/Ensemble/).length).toBeGreaterThan(0)
    expect(within(section).getAllByText(/games and \d+ seasons/, { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('better than the market', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /What history would change/ })).toBeInTheDocument()
    expect(screen.getByText(/History would move \d+ of the \w+'s 100 attention points/)).toBeInTheDocument()
  })

  it('calibration tab: a verdict per line', async () => {
    renderRoute('/tracker?tab=calibration')
    expect(await screen.findByText(/The Analyst: (well calibrated|overconfident by \d+ points|underconfident by \d+ points)/)).toBeInTheDocument()
  })

  it('disagreements tab: divergence sentences', async () => {
    renderRoute('/tracker?tab=disagreements')
    expect(await screen.findByText(/In [\d,]+ games where the Traditionalist disagreed with the market by less than 2.5 points/)).toBeInTheDocument()
  })

  it('bets tab: the ledger', async () => {
    renderRoute('/tracker?tab=bets')
    expect(await screen.findByRole('heading', { name: /Paper bets/ })).toBeInTheDocument()
    expect(screen.getByText(/Not betting advice; small samples/)).toBeInTheDocument()
  })
})
