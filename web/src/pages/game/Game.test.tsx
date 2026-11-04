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
    // summary strip, then the matchup with no approach in it (the default before kickoff)
    expect(screen.getByRole('group', { name: 'Game summary' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Preview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: /^Who has the edge/ })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Home win chance for GB: market/ })).toBeNull()
    // the approaches, one tab over
    await userEvent.click(screen.getByRole('tab', { name: 'Approaches' }))
    expect(screen.getByRole('img', { name: /Home win chance for GB: market/ })).toBeInTheDocument()
    expect(screen.getByText(/Inside each group/)).toBeInTheDocument()
    expect(screen.getAllByText(/toward GB/).length).toBeGreaterThan(0)
    // tendencies have their own tab
    await userEvent.click(screen.getByRole('tab', { name: 'Tendencies' }))
    expect(screen.getByText('CAR offense vs GB defense')).toBeInTheDocument()
    expect(screen.getByText('Defensive habits')).toBeInTheDocument()
    // narrative, on the news tab
    await userEvent.click(screen.getByRole('tab', { name: 'Injuries & news' }))
    expect(screen.getByText(/What people are saying about the matchup/)).toBeInTheDocument()
    expect(screen.getByText(/Carolina's run defense is among the league's worst/)).toBeInTheDocument()
    expect(screen.getByText(/claude-code\/sonnet-5.5/)).toBeInTheDocument()
    expect(screen.getByText(/Claims and sources/)).toBeInTheDocument()
  })

  it('switches approach and situation', async () => {
    renderRoute('/game/2026_08_CAR_GB')
    await screen.findByText(/Lambeau Field/)
    await userEvent.click(screen.getByRole('tab', { name: 'Approaches' }))
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Approach' })).getByRole('radio', { name: 'Analyst' }))
    expect(screen.getByText(/Analyst says: GB win chance 71.2%/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Tendencies' }))
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Situation' })).getByRole('radio', { name: 'Third down' }))
    expect(screen.getByRole('radio', { name: 'Third down' })).toHaveAttribute('aria-checked', 'true')
  })

  it('labels a game scored without a lock as not locked', async () => {
    renderRoute('/game/2026_08_ARI_DAL?tab=approaches')
    expect(await screen.findByText(/Not locked: no lock was recorded/)).toBeInTheDocument()
  })

  it('overlays an approach on the Preview bars and keeps the fit unnamed', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB')
    await screen.findByRole('heading', { name: /^Who has the edge/ })
    expect(container.querySelector('[data-testid="overlay"]')).toBeNull()
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Overlay an approach' })).getByRole('radio', { name: 'Analyst' }))
    expect(screen.getByText(/how the Analyst reads each part/)).toBeInTheDocument()
    expect(container.querySelectorAll('[data-testid="overlay"]').length).toBeGreaterThan(0)
    expect(container.textContent).not.toMatch(/Global/)
  })

  it('draws the tape on league bands and says how many gaps stand out', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB?tab=details')
    expect(await screen.findByText(/of these \d+ gaps stands? out/)).toBeInTheDocument()
    expect(container.querySelectorAll('[data-testid="band"]').length).toBeGreaterThan(0)
  })

  it('shows "no narrative" for a game without one', async () => {
    renderRoute('/game/2026_08_ARI_DAL?tab=news')
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

    it('opens a finished game on the retrospective, with the post-game summary', async () => {
      renderRoute('/game/2026_08_CAR_GB', root)
      expect(await screen.findByRole('heading', { name: /^How the forecasts did/ })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: /^Which groups mattered/ })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'What happened' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByLabelText('Final: CAR 23, GB 20')).toBeInTheDocument()
      const strip = screen.getByRole('group', { name: 'Game summary' })
      expect(within(strip).getByText('Approaches right')).toBeInTheDocument()
      expect(within(strip).getByText('0 of 4')).toBeInTheDocument()
      // what the approaches said is two tabs over
      expect(screen.queryByRole('img', { name: /Home win chance for GB/ })).toBeNull()
      await userEvent.click(screen.getByRole('tab', { name: 'Approaches' }))
      expect(screen.getByRole('img', { name: /Home win chance for GB: market/ })).toBeInTheDocument()
    })

    it('switches tabs from a summary tile', async () => {
      renderRoute('/game/2026_08_CAR_GB?tab=news', root)
      await screen.findByRole('tab', { name: 'Injuries & news' })
      await userEvent.click(within(screen.getByRole('group', { name: 'Game summary' })).getByText('Played like'))
      expect(screen.getByRole('tab', { name: 'What happened' })).toHaveAttribute('aria-selected', 'true')
    })

    it('renders nothing extra when there is no retro for the game', async () => {
      fs.rmSync(path.join(root, 'site/retro'), { recursive: true, force: true })
      renderRoute('/game/2026_08_CAR_GB', root)
      expect(await screen.findByText(/Lambeau Field/)).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: /^How the forecasts did/ })).toBeNull()
      expect(screen.queryByRole('tab', { name: 'What happened' })).toBeNull()
      expect(screen.getByRole('tab', { name: 'Preview' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.queryByRole('alert')).toBeNull()
    })

    it('does not ask for a retro on a game without a result', async () => {
      renderRoute('/game/2026_08_ARI_DAL?tab=approaches')
      expect(await screen.findByText(/Not locked: no lock was recorded/)).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: /^How the forecasts did/ })).toBeNull()
    })
  })
})
