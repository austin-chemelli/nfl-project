import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterAll, describe, expect, it } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
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
    await userEvent.click(screen.getByRole('tab', { name: 'Matchups' }))
    expect(screen.getByText('CAR offense vs GB defense')).toBeInTheDocument()
    expect(screen.getByText(/When CAR has the ball/)).toBeInTheDocument()
    // narrative, on the news tab
    await userEvent.click(screen.getByRole('tab', { name: 'Injuries & news' }))
    expect(screen.getByText(/What people are saying about the matchup/)).toBeInTheDocument()
    expect(screen.getByText(/Carolina's run defense is among the league's worst/)).toBeInTheDocument()
    expect(screen.getByText(/claude-code\/sonnet-5.5/)).toBeInTheDocument()
    expect(screen.getByText(/Claims and sources/)).toBeInTheDocument()
  })

  it('the Matchups tab leads with the lede, then per side of the ball the face-off and the habits', async () => {
    renderRoute('/game/2026_08_CAR_GB?tab=tendencies')
    expect(await screen.findByText(/^The biggest mismatch: GB's pass defense \(4th\) against CAR's passing offense \(22nd\)\./)).toBeInTheDocument()
    expect(screen.getAllByTestId('side-title').map((h) => h.textContent)).toEqual([expect.stringMatching(/^When GB has the ball/), expect.stringMatching(/^When CAR has the ball/)])
    expect(screen.getAllByTestId('face-off')).toHaveLength(2)
    expect(screen.getAllByTestId('habit-list')).toHaveLength(2)
    expect(screen.queryByText('Defensive habits')).toBeNull() // the tendency charts are folded in
    expect(screen.getAllByText(/at least eight places better/)).toHaveLength(1)
  })

  it('without matchups the tab shows the tendencies as before', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nfl-nomatchups-'))
    fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
    const gp = path.join(root, 'site/game/2026_08_CAR_GB.json')
    const game = JSON.parse(fs.readFileSync(gp, 'utf8'))
    game.matchups = null
    fs.writeFileSync(gp, JSON.stringify(game))
    renderRoute('/game/2026_08_CAR_GB?tab=tendencies', root)
    expect(await screen.findByText('Defensive habits')).toBeInTheDocument()
    expect(screen.queryByTestId('face-off')).toBeNull()
    expect(screen.queryByText(/Ranks are this season's games/)).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('switches approach', async () => {
    renderRoute('/game/2026_08_CAR_GB')
    await screen.findByText(/Lambeau Field/)
    await userEvent.click(screen.getByRole('tab', { name: 'Approaches' }))
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Approach' })).getByRole('radio', { name: 'Analyst' }))
    expect(screen.getByText(/Analyst says: GB win chance 71.2%/)).toBeInTheDocument()
  })

  it('labels a game scored without a lock as not locked', async () => {
    renderRoute('/game/2026_08_ARI_DAL?tab=approaches')
    expect(await screen.findByText(/Not locked: no lock was recorded/)).toBeInTheDocument()
  })

  it('the Preview is a card per tab, approach-free, each card linking to its tab', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB')
    await screen.findByRole('heading', { name: /^Who has the edge/ })
    expect(screen.queryByRole('radiogroup', { name: 'Overlay an approach' })).toBeNull()
    expect(container.querySelector('[data-testid="overlay"]')).toBeNull()
    expect(container.textContent).not.toMatch(/Global/)
    const hub = screen.getByTestId('preview-hub')
    const cards = [...hub.querySelectorAll('section[data-testid^="teaser-"]')].map((s) => s.getAttribute('data-testid'))
    expect(cards).toEqual(['teaser-matchup', 'teaser-edge', 'teaser-line', 'teaser-news', 'teaser-tape'])
    // both teams' edge cards, compact, the underdog first
    expect(within(screen.getByTestId('teaser-matchup')).getAllByRole('heading', { name: /^Where \w+ has the edge/ }).map((h) => h.textContent)).toEqual([
      expect.stringMatching(/^Where CAR has the edge/),
      expect.stringMatching(/^Where GB has the edge/),
    ])
    expect(within(screen.getByTestId('teaser-line')).getByText(/books disagree/i)).toBeInTheDocument()
    expect(within(screen.getByTestId('teaser-tape')).getAllByRole('listitem')).toHaveLength(3)
    for (const [card, tab] of [['teaser-matchup', 'Matchups'], ['teaser-edge', 'Approaches'], ['teaser-line', /^The line/], ['teaser-news', 'Injuries & news'], ['teaser-tape', 'Details']] as const) {
      await userEvent.click(within(screen.getByTestId(card)).getByRole('button', { name: /→$/ }))
      expect(screen.getByRole('tab', { name: tab })).toHaveAttribute('aria-selected', 'true')
      await userEvent.click(screen.getByRole('tab', { name: 'Preview' }))
    }
  })

  it('"Who has the edge" in full, with the live-only parts as bars of their own, opens the Approaches tab', async () => {
    renderRoute('/game/2026_08_CAR_GB?tab=approaches')
    await screen.findByRole('heading', { name: /^Who has the edge/ })
    expect(screen.queryByRole('button', { name: 'By approach →' })).toBeNull() // it is this tab now
    const live = screen.getByTestId('live-only')
    expect(within(live).getByText('This week only')).toBeInTheDocument()
    for (const name of ['Market behavior', 'Buzz', 'Line movement', 'Public betting on the home team', 'Media sentiment', 'Hype']) expect(within(live).getAllByText(name).length).toBeGreaterThan(0) // the fixture has every reading
    expect(within(live).getAllByText('51% on GB').length).toBeGreaterThan(0)
    expect(within(live).getAllByText('0.0 pts').length).toBeGreaterThan(0) // no line move is a zero bar, not words
  })

  it('the line has its own tab, with each book and a flag when they disagree', async () => {
    renderRoute('/game/2026_08_CAR_GB')
    await screen.findByRole('heading', { name: /^Who has the edge/ })
    expect(screen.queryByRole('heading', { name: /^How the line moved/ })).toBeNull() // not on the Preview
    const tab = screen.getByRole('tab', { name: /^The line: books disagree$/ })
    await userEvent.click(tab)
    expect(screen.getByRole('heading', { name: /^How the line moved/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^What each sportsbook says/ })).toBeInTheDocument()
    expect(screen.getByTestId('books-read')).toHaveTextContent(/Books split on the spread: The books sit on both sides of 3, a key number: GB −3 at DraftKings, GB −4 at FanDuel/)
    expect(screen.getByRole('cell', { name: 'BetMGM' })).toBeInTheDocument()
  })

  it('names each QB under its team, links the Preview to the Approaches tab, and builds the narrative help from the record', async () => {
    renderRoute('/game/2026_08_CAR_GB')
    expect(await screen.findByText(/CAR Bryce Young · GB /)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Every factor and approach →' }))
    expect(screen.getByRole('tab', { name: 'Approaches' })).toHaveAttribute('aria-selected', 'true')
    await userEvent.click(screen.getByRole('tab', { name: 'Injuries & news' }))
    expect(screen.getByText(/This week's coverage, as of \w{3}, \w{3} \d+\. It never feeds the probabilities\./)).toBeInTheDocument()
    expect(screen.getByText(/Written by a language model \(claude-code\/sonnet-5.5, /)).toBeInTheDocument()
  })

  it('has no line tab until there is a line or three books', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nfl-noline-'))
    fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
    const gp = path.join(root, 'site/game/2026_08_CAR_GB.json')
    const game = JSON.parse(fs.readFileSync(gp, 'utf8'))
    Object.assign(game, { market_history: [], line_move: null, books: null })
    fs.writeFileSync(gp, JSON.stringify(game))
    renderRoute('/game/2026_08_CAR_GB', root)
    await screen.findByRole('tab', { name: 'Preview' })
    expect(screen.queryByRole('tab', { name: /^The line/ })).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('the Approaches tab outlines what history says on each approach\'s bars', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB?tab=approaches')
    await screen.findByRole('heading', { name: /^Why they lean/ })
    expect(container.querySelectorAll('[data-testid="overlay"]').length).toBeGreaterThan(0)
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Approach' })).getByRole('radio', { name: 'Sharp' }))
    expect(container.querySelectorAll('[data-testid="overlay"]').length).toBeGreaterThan(0)
    expect(container.textContent).not.toMatch(/Global/)
  })

  it('never shows a push toward a team as a negative number', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB?tab=approaches')
    await screen.findByRole('heading', { name: /^Why they lean/ })
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Approach' })).getByRole('radio', { name: 'Sharp' }))
    const chart = [...container.querySelectorAll('section svg[role="img"]')].find((x) => /toward/.test(x.textContent ?? ''))!
    expect(chart.textContent).toMatch(/\+\d+\.\d pts/)
    expect(chart.textContent).not.toMatch(/[−-]\d/)
  })

  it('draws the tape on league bands and says how many gaps stand out', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB?tab=details')
    expect(await screen.findByText(/\d+ of \d+ gaps stands? out/)).toBeInTheDocument()
    expect(container.querySelectorAll('[data-testid="band"]').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('[data-testid="band-core"]').length).toBeGreaterThan(0)
  })

  it('a hovered band row shows both teams and where the league sits; it leaves with the pointer', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB?tab=details')
    await screen.findByText(/\d+ of \d+ gaps stands? out/)
    const row = container.querySelector('svg g[tabindex]')!
    fireEvent.pointerMove(row, { clientX: 40, clientY: 10 })
    const tip = await screen.findByTestId('chart-tip')
    expect(tip).toHaveTextContent(/CAR/)
    expect(tip).toHaveTextContent(/GB/)
    expect(tip).toHaveTextContent(/League median/)
    fireEvent.pointerLeave(row)
    expect(screen.queryByTestId('chart-tip')).toBeNull()
  })

  it('a band row shows the same card on keyboard focus', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB?tab=details')
    await screen.findByText(/\d+ of \d+ gaps stands? out/)
    fireEvent.focus(container.querySelector('svg g[tabindex]')!)
    expect(await screen.findByTestId('chart-tip')).toHaveTextContent(/League median/)
  })

  it('wears the matchup colors from the banner down', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB')
    await screen.findByRole('heading', { name: /^Who has the edge/ })
    const scope = container.querySelector<HTMLElement>('[data-matchup]')!
    expect(scope.style.getPropertyValue('--team-away-dark')).toMatch(/^#/)
    expect(scope.style.getPropertyValue('--team-home-light')).toMatch(/^#/)
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

describe('Game loading', () => {
  it('shows the page shape while the game is pending', async () => {
    const { container } = renderRoute('/game/2026_08_CAR_GB')
    await screen.findByRole('status', { name: 'Loading game…' })
    expect(container.querySelectorAll('[data-skeleton="tile"]')).toHaveLength(5)
    expect(container.querySelector('[data-skeleton="tabs"]')).not.toBeNull()
    await screen.findByText(/Lambeau Field/)
  })
})
