import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LeagueFile } from '../../data/contract'
import { renderRoute } from '../../test/render'
import { stakesLine } from './helpers'

/** A copy of the fixtures where the listed weeks' slates have a finished game, so their recap is requested. */
export function fixturesWithResults(weeks: number[]): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'slate-recap-'))
  fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
  const base = JSON.parse(fs.readFileSync(path.join(root, 'site/slate_2026_08.json'), 'utf8'))
  for (const w of weeks) {
    const d = structuredClone(base)
    d.week = w
    d.games[0].result = { home_score: 23, away_score: 20, margin: 3 }
    fs.writeFileSync(path.join(root, `site/slate_2026_${String(w).padStart(2, '0')}.json`), JSON.stringify(d))
  }
  return root
}

describe('Slate page', () => {
  it('renders the week-8 games with picks, line and market', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.getAllByText('ARI').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /Week 8/ })).toBeInTheDocument()
    // Fixture: market GB 64%, line GB −3.5
    const card = screen.getByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(card).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    expect(within(card).getByText(/market GB 64%/)).toBeInTheDocument()
    expect(within(card).getByText(/GB −3.5/)).toBeInTheDocument()
    expect(within(card).getByText("Student's pick: GB 72%")).toBeInTheDocument()
    expect(within(card).getByRole('img')).toHaveAccessibleName(/market 64%.*Student \d+%/)
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
    expect(screen.getByRole('radio', { name: 'Student vs market' })).toHaveAttribute('aria-checked', 'true')
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

  it('titles the tab for the page', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(document.title).toBe('This week · NFL approaches')
  })

  it('titles the tab for an explicit week', async () => {
    renderRoute('/week/2026/9')
    await screen.findByText(/No slate for 2026 week 9/)
    expect(document.title).toBe('Week 9, 2026 · NFL approaches')
  })

  it('shows last week\'s line on the current week only', async () => {
    const root = fixturesWithResults([7])
    fs.copyFileSync(path.join(root, 'site/recap_2026_08.json'), path.join(root, 'site/recap_2026_07.json'))
    renderRoute('/', root)
    const link = await screen.findByRole('link', { name: /^Last week( \(backfill\))?: Student \d+ of \d+ right, market \d+ of \d+\.$/ })
    expect(link).toHaveAttribute('href', '/week/2026/7')
    fs.rmSync(root, { recursive: true, force: true })
  })

  it.each([
    ['backfill', /scored after the fact\./],
    ['locked', /^Picks come from the locks/],
  ])('says in a hover when last week was %s', async (status, tip) => {
    const root = fixturesWithResults([7])
    fs.copyFileSync(path.join(root, 'site/recap_2026_08.json'), path.join(root, 'site/recap_2026_07.json'))
    const file = path.join(root, 'site/slate_2026_07.json')
    const slate = JSON.parse(fs.readFileSync(file, 'utf8'))
    for (const g of slate.games) for (const m of Object.values<{ status: string }>(g.models)) m.status = status
    fs.writeFileSync(file, JSON.stringify(slate))
    renderRoute('/', root)
    expect(await screen.findByRole('link', { name: status === 'locked' ? /^Last week: / : /^Last week \(backfill\): / })).toBeInTheDocument()
    expect(screen.getByText(tip)).toBeInTheDocument()
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('shows no last-week line on the current week without a recap, or on another week', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.queryByText(/Last week:/)).toBeNull()
    const root = fixturesWithResults([7])
    fs.copyFileSync(path.join(root, 'site/recap_2026_08.json'), path.join(root, 'site/recap_2026_07.json'))
    renderRoute('/week/2026/7', root)
    await screen.findAllByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.queryByText(/Last week:/)).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('opens an explicit week and shows a friendly message for a missing slate', async () => {
    renderRoute('/week/2026/9')
    expect(await screen.findByText(/No slate for 2026 week 9/)).toBeInTheDocument()
  })

  it('week picker navigates', async () => {
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    await userEvent.click(screen.getByRole('button', { name: 'Next week' }))
    expect(await screen.findByText(/No slate for 2026 week 9/)).toBeInTheDocument()
  })

  it('shows the why line, and the tendencies contrast when stark, on a pregame card', async () => {
    renderRoute('/')
    const card = await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(within(card).getByText('GB quality edge, 92nd pct')).toBeInTheDocument()
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
    expect(within(card).queryByText(/edge, \d+\w+ pct/)).toBeNull()
    expect(within(card).queryByText(/most blitz-heavy/)).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })
})

describe('Slate stakes line', () => {
  const fix = path.resolve(import.meta.dirname, '../../test/fixtures/site')
  it('shows the Student-only line on a card, computed from the league fixture', async () => {
    const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(fix, 'league.json'), 'utf8')))
    const slate = JSON.parse(fs.readFileSync(path.join(fix, 'slate_2026_08.json'), 'utf8'))
    const expected = slate.games.flatMap((g: { game_id: string }) => stakesLine(g, league) ?? [])
    expect(expected.length).toBeGreaterThan(0)
    renderRoute('/')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    await screen.findAllByText(/^Playoff stakes: /)
    expect(screen.getAllByText(/^Playoff stakes: /)).toHaveLength(expected.length)
    for (const line of expected) expect(screen.getByText(line)).toBeInTheDocument()
  })

  it('shows no line and no error when league.json is missing', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'slate-nolg-'))
    fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
    fs.rmSync(path.join(root, 'site/league.json'))
    renderRoute('/', root)
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.queryByText(/Playoff stakes/)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })
})

describe('Slate loading', () => {
  it('shows tiles and matchup-card blocks while pending', async () => {
    const { container } = renderRoute('/')
    await screen.findByRole('status', { name: 'Loading slate…' })
    expect(container.querySelectorAll('[data-skeleton="tile"]')).toHaveLength(5)
    expect(container.querySelectorAll('[data-skeleton="card"]').length).toBeGreaterThan(1)
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
  })
})
