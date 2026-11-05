import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
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

  it('shows the why line, and the tendencies contrast when stark, on a pregame card', async () => {
    renderRoute('/')
    const card = await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(within(card).getByText('GB Quality edge, bigger than 92% of matchups')).toBeInTheDocument()
    expect(within(card).getByText("The league's 3rd-most pass-heavy offense (GB) faces its most blitz-heavy defense (CAR)")).toBeInTheDocument()
    expect(within(card).getByText(/total 47.5/)).toBeInTheDocument()
    const bal = screen.getByRole('link', { name: /^BAL\s*@\s*BUF\s*\S/ })
    expect(within(bal).getByText('Tyler Huntley listed to start for BAL (usually Lamar Jackson) · BUF without A Receiver (WR)')).toBeInTheDocument()
    // the link reads the teams and kickoff, then the why line as its description, not the whole card
    expect(bal).toHaveAccessibleName(/^BAL\s*@\s*BUF.*ET/)
    expect(bal.getAttribute('aria-labelledby')).toBeTruthy()
    expect(bal).toHaveAccessibleDescription('Tyler Huntley listed to start for BAL (usually Lamar Jackson) · BUF without A Receiver (WR)')
    expect(within(screen.getByRole('link', { name: /^MIN\s*@\s*DET\s*\S/ })).queryByText('Weather could be a factor')).toBeNull()
    expect(within(screen.getByRole('link', { name: /^KC\s*@\s*DEN\s*\S/ })).getByText('No standout edge')).toBeInTheDocument()
  })

  it('still renders a game with no card, and nothing nests inside the link', async () => {
    renderRoute('/')
    const card = await screen.findByRole('link', { name: /^ARI\s*@\s*DAL\s*\S/ })
    expect(within(card).queryByText(/edge|without|listed to start|No standout/)).toBeNull()
    expect(within(card).getByText(/total/)).toBeInTheDocument()
    for (const a of screen.getAllByRole('link', { name: /^[A-Z]+\s*@\s*[A-Z]+.*(ET|Final)/ })) {
      expect(a.querySelector('a, button')).toBeNull()
    }
  })

  it('keeps the sentence on finished cards and skips the pregame lines', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'slate-fix-'))
    fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
    const f = path.join(root, 'site/slate_2026_08.json')
    const d = JSON.parse(fs.readFileSync(f, 'utf8'))
    const g = d.games.find((x: { game_id: string }) => x.game_id === '2026_08_CAR_GB')
    g.result = { home_score: 23, away_score: 20, margin: 3 }
    fs.writeFileSync(f, JSON.stringify(d))
    renderRoute('/', root)
    const card = await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(within(card).getByText(/Final/)).toBeInTheDocument()
    expect(within(card).getByText(/picked|called it|missed it|Upset|Approaches/)).toBeInTheDocument()
    expect(within(card).queryByText(/edge, bigger than/)).toBeNull()
    expect(within(card).queryByText(/most blitz-heavy/)).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })
})
