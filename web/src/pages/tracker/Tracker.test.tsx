import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'
import type { Meta, Tracker } from '../../data/contract'
import { Ledger } from './Ledger'

describe('Tracker page', () => {
  it('shows the five-tile strip and the season tab by default', async () => {
    renderRoute('/tracker')
    const strip = await screen.findByRole('group', { name: 'Tracker summary' })
    expect(within(strip).getAllByRole('button')).toHaveLength(5)
    expect(await screen.findByText(/^After \d+ games, the Student is/)).toBeInTheDocument()
    expect(screen.getByText(/No live locks have been graded yet/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Log loss by season/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Backtest: how far/ })).not.toBeInTheDocument()
  })

  it('has exactly four tabs', async () => {
    renderRoute('/tracker')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((x) => x.textContent)).toEqual(['This season', 'Backtest', 'Calibration', 'Paper bets'])
  })

  it('season tab: the gap chart says which way is good and draws the noise band', async () => {
    renderRoute('/tracker')
    expect(await screen.findByText('ahead of the market ↑')).toBeInTheDocument()
    expect(screen.getByText('behind ↓')).toBeInTheDocument()
    expect(screen.getByText('too close to call')).toBeInTheDocument()
    expect(screen.queryByText(/live from week/)).not.toBeInTheDocument()
    expect(screen.queryByText('backfill')).not.toBeInTheDocument()
    // the market is the zero line, not a toggle
    const toggles = screen.getByRole('group', { name: 'Lines to show' })
    expect(within(toggles).queryByText('Market')).toBeNull()
  })

  it('season tab: a live week draws a dashed line labeled with its week', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'tracker-live-'))
    fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
    const file = path.join(root, 'site/tracker.json')
    const t = JSON.parse(fs.readFileSync(file, 'utf8'))
    for (const r of t.current_season) if (r.week >= 6) r.live = true
    fs.writeFileSync(file, JSON.stringify(t))
    try {
      renderRoute('/tracker', root)
      expect(await screen.findByText('live from week 6')).toBeInTheDocument()
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
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
    expect(within(section).getAllByText(/Student/).length).toBeGreaterThan(0)
    expect(within(section).queryByText(/Ensemble/)).toBeNull()
    expect(within(section).getAllByText(/games and \d+ seasons/, { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('better than the market', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /What history would change/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Log loss by season/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /When an approach disagrees with the market/ })).toBeInTheDocument()
    expect(screen.getByText(/History would move \d+ of the \w+'s 100 attention points/)).toBeInTheDocument()
  })

  it('calibration tab: a verdict per line', async () => {
    renderRoute('/tracker?tab=calibration')
    expect(await screen.findByText(/The Analyst: (well calibrated|overconfident by \d+ points|underconfident by \d+ points)/)).toBeInTheDocument()
  })

  it('backtest tab: the disagreement table for the selected approach, with no chart', async () => {
    renderRoute('/tracker?tab=backtest')
    const h = await screen.findByRole('heading', { name: /When an approach disagrees with the market/ })
    const section = h.closest('section')!
    expect(within(section).getByRole('columnheader', { name: 'Disagreement' })).toBeInTheDocument()
    expect(within(section).getByRole('columnheader', { name: 'Log loss vs market' })).toBeInTheDocument()
    expect(within(section).getAllByRole('row').length).toBeGreaterThan(1)
    expect(section.querySelector('.recharts-wrapper')).toBeNull()
  })

  it('the disagreement table opens on the headline line', async () => {
    renderRoute('/tracker?tab=backtest')
    const h = await screen.findByRole('heading', { name: /When an approach disagrees with the market/ })
    const group = within(h.closest('section')!).getByRole('radiogroup', { name: 'Approach' })
    expect(within(group).getByRole('radio', { name: 'Student' })).toHaveAttribute('aria-checked', 'true')
  })

  it('backtest rows leave out the global diagnostic', async () => {
    renderRoute('/tracker?tab=backtest')
    const h = await screen.findByRole('heading', { name: /Backtest: how far/ })
    expect(within(h.closest('section')!).queryByText(/^Global$/)).toBeNull()
  })

  it('the removed disagreements tab falls back to the default', async () => {
    renderRoute('/tracker?tab=disagreements')
    expect(await screen.findByText(/^After \d+ games, the Student is/)).toBeInTheDocument()
  })

  it('the ledger shows no diagnostic, though the file can carry one', () => {
    const row = (model_id: string, bets: number) => ({ model_id, kind: 'backfill', bets, wins: 1, losses: 1, pushes: 0, units: 0, roi: 0, clv: 0 })
    render(<Ledger t={{ ledger: [row('student', 11), row('ensemble', 22), row('global', 33)] } as unknown as Tracker} meta={{ approaches: [] } as unknown as Meta} />)
    expect(screen.getByText('11')).toBeInTheDocument()
    expect(screen.queryByText('22')).toBeNull()
    expect(screen.queryByText('33')).toBeNull()
  })

  it('bets tab: the ledger', async () => {
    renderRoute('/tracker?tab=bets')
    expect(await screen.findByRole('heading', { name: /Paper bets/ })).toBeInTheDocument()
    expect(screen.getByText(/Not betting advice; small samples/)).toBeInTheDocument()
  })

  it('bets tab: says how the lines did, with the bankroll, the returns and the seasons', async () => {
    renderRoute('/tracker?tab=bets')
    expect(await screen.findByText(/^In the backtest, every approach has lost money\. The best, the Sharp/)).toBeInTheDocument()
    for (const name of ['Bankroll over time', 'Return per bet', 'Season by season']) expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Lines to show' })).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: /Sharp/ })).toBeInTheDocument()
  })

  it('shows CLV only once a live bet has one', () => {
    const row = (kind: string, clv: number | null) => ({ model_id: 'student', kind, bets: 1, wins: 1, losses: 0, pushes: 0, units: 1, roi: 1, clv })
    const meta = { approaches: [] } as unknown as Meta
    const { unmount } = render(<Ledger t={{ ledger: [row('backfill', null)] } as unknown as Tracker} meta={meta} />)
    expect(screen.queryByText('CLV')).toBeNull()
    unmount()
    render(<Ledger t={{ ledger: [row('backfill', null), row('live', 0.012)] } as unknown as Tracker} meta={meta} />)
    expect(screen.getByText('CLV')).toBeInTheDocument()
    expect(screen.getByText('+1.20%')).toBeInTheDocument()
  })
})

describe('Tracker loading', () => {
  it('shows the page shape (tiles and tabs) while the data is pending', async () => {
    const { container } = renderRoute('/tracker')
    const status = await screen.findByRole('status', { name: 'Loading tracker…' })
    expect(status).toBeInTheDocument()
    expect(container.querySelectorAll('[data-skeleton="tile"]')).toHaveLength(5)
    expect(container.querySelector('[data-skeleton="tabs"]')).not.toBeNull()
    await screen.findByRole('group', { name: 'Tracker summary' })
  })
})
