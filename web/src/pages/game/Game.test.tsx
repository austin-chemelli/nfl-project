import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterAll, describe, expect, it } from 'vitest'
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

  it('labels a game scored without a lock as not locked', async () => {
    renderRoute('/game/2026_08_ARI_DAL')
    expect(await screen.findByText(/Not locked: no lock was recorded/)).toBeInTheDocument()
  })

  it('shows "no narrative" for a game without one', async () => {
    renderRoute('/game/2026_08_ARI_DAL')
    expect(await screen.findByText(/No narrative research for this game yet/)).toBeInTheDocument()
  })

  it('is friendly when the game file is missing', async () => {
    renderRoute('/game/2026_08_AAA_BBB')
    expect(await screen.findByText(/No detail file for this game yet/)).toBeInTheDocument()
  })

  describe('retrospective', () => {
    // a copy of the fixtures where CAR @ GB has a final score, so the shared game file stays untouched
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nfl-retro-'))
    const src = path.resolve(import.meta.dirname, '../../test/fixtures')
    fs.cpSync(src, root, { recursive: true })
    const gp = path.join(root, 'site/game/2026_08_CAR_GB.json')
    const game = JSON.parse(fs.readFileSync(gp, 'utf8'))
    game.result = { home_score: 20, away_score: 23, margin: -3 }
    fs.writeFileSync(gp, JSON.stringify(game))
    afterAll(() => fs.rmSync(root, { recursive: true, force: true }))

    it('renders the retrospective at the top of a finished game', async () => {
      renderRoute('/game/2026_08_CAR_GB', root)
      expect(await screen.findByRole('heading', { name: /^How the forecasts did/ })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: /^Which groups mattered/ })).toBeInTheDocument()
      // above the approaches chart
      const retro = screen.getByRole('heading', { name: /^How the forecasts did/ })
      const chart = screen.getByRole('img', { name: /Home win chance for GB by model/ })
      expect(retro.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    it('renders nothing extra when there is no retro for the game', async () => {
      fs.rmSync(path.join(root, 'site/retro'), { recursive: true, force: true })
      renderRoute('/game/2026_08_CAR_GB', root)
      expect(await screen.findByText(/Lambeau Field/)).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: /^How the forecasts did/ })).toBeNull()
      expect(screen.queryByRole('alert')).toBeNull()
    })

    it('does not ask for a retro on a game without a result', async () => {
      renderRoute('/game/2026_08_ARI_DAL')
      expect(await screen.findByText(/Not locked: no lock was recorded/)).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: /^How the forecasts did/ })).toBeNull()
    })
  })
})
