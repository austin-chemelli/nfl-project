import { cleanup, render, screen, within } from '@testing-library/react'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import userEvent from '@testing-library/user-event'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { LeagueFile } from '../../data/contract'
import { renderRoute } from '../../test/render'
import { MemoryRouter } from 'react-router'
import { Games } from './Games'
import { Odds } from './Odds'
import { LATER_GAMES } from './playoffs'

// a day before the fixture's first kickoff: the page only lists games still to come
const FIXTURE_NOW = new Date('2026-10-31T12:00:00Z')
beforeAll(() => { vi.useFakeTimers({ toFake: ['Date'], now: FIXTURE_NOW }) })
afterAll(() => { vi.useRealTimers() })

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures')
const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'site/league.json'), 'utf8')))

/** The fixtures without league.json. */
function withoutLeague(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-nolg-'))
  fs.cpSync(FIX, root, { recursive: true })
  fs.rmSync(path.join(root, 'site/league.json'))
  return root
}

describe('League page, playoff tabs', () => {
  it('shows the five tabs in order, Playoff odds first and selected, and a summary strip', async () => {
    renderRoute('/league')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['Playoff odds', 'Team charts', 'Standings', 'Games that matter', 'Similar seasons'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    const strip = await screen.findByRole('group', { name: 'League summary' })
    expect(within(strip).getAllByRole('button')).toHaveLength(4)
  })

  it('opens a tab from its URL and a tile from a click', async () => {
    renderRoute('/league')
    const strip = await screen.findByRole('group', { name: 'League summary' })
    await userEvent.click(within(strip).getByRole('button', { name: /Biggest game this week/ }))
    expect(await screen.findByRole('tab', { name: 'Games that matter' })).toHaveAttribute('aria-selected', 'true')
  })

  it('Odds: both conferences and both views, URL-synced, sorted, one rule after the 7th row', async () => {
    renderRoute('/league?tab=odds')
    const list = await screen.findByRole('list', { name: 'AFC playoff odds' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(16)
    const afc = league.teams.filter((t) => t.conf === 'AFC').map((t) => t.team).sort((a, b) => league.odds.student.teams[b].playoffs - league.odds.student.teams[a].playoffs || a.localeCompare(b))
    expect(rows.map((r) => r.getAttribute('data-team'))).toEqual(afc)
    expect(rows.filter((r) => r.className.includes('border-t-2'))).toHaveLength(1)
    expect(rows[7].className).toContain('border-t-2')

    await userEvent.click(screen.getByRole('radio', { name: 'NFC' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Market' }))
    const nfc = within(await screen.findByRole('list', { name: 'NFC playoff odds' })).getAllByRole('listitem')
    const order = league.teams.filter((t) => t.conf === 'NFC').map((t) => t.team).sort((a, b) => league.odds.market.teams[b].playoffs - league.odds.market.teams[a].playoffs || a.localeCompare(b))
    expect(nfc.map((r) => r.getAttribute('data-team'))).toEqual(order)
    expect(screen.getByRole('radio', { name: 'Market' })).toHaveAttribute('aria-checked', 'true')
  })

  it('Odds: restores the toggles from the URL', async () => {
    renderRoute('/league?tab=odds&conf=NFC&view=market')
    await screen.findByRole('list', { name: 'NFC playoff odds' })
    expect(screen.getByRole('radio', { name: 'Market' })).toHaveAttribute('aria-checked', 'true')
  })

  it('Odds: team bars use the team color slot, not a raw color, and no probability reads 0% or 100%', async () => {
    const { container } = renderRoute('/league?tab=odds')
    const list = await screen.findByRole('list', { name: 'AFC playoff odds' })
    const row = within(list).getAllByRole('listitem')[0]
    expect(row).toHaveAttribute('data-matchup')
    expect(row.style.getPropertyValue('--team-home-light')).toMatch(/^#/) // set by teamDotVars, so the fill has a color
    expect(row.querySelector('[style*="var(--team-home)"]')).not.toBeNull()
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/(^|[^.\d])(0|100)%/)
    expect(text).toMatch(/<0\.1%|>99\.9%/)
    expect(text).not.toMatch(/clinch|eliminat/i)
  })

  it('Odds: rounds show on hover', async () => {
    renderRoute('/league?tab=odds')
    const row = within(await screen.findByRole('list', { name: 'AFC playoff odds' })).getAllByRole('listitem')[0]
    await userEvent.hover(row)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Win the Super Bowl')
  })

  it('Odds: one fine print block, with the file\'s counts and how the estimate tested', async () => {
    renderRoute('/league?tab=odds')
    await screen.findByRole('list', { name: 'AFC playoff odds' })
    expect(document.querySelectorAll('details summary').length).toBeGreaterThan(0)
    const fine = screen.getByText('How these odds are made').closest('details')!
    expect(fine).toHaveTextContent(`${league.odds.student.sources.locked} from its locked picks`)
    expect(fine).toHaveTextContent('missed by about 7 points')
    expect(fine).not.toHaveTextContent('own units')
    expect(fine).toHaveTextContent('2002 to 2025')
    expect(screen.getAllByText('How these odds are made')).toHaveLength(1)
  })

  it('Standings: eight division tables with the six columns', async () => {
    renderRoute('/league?tab=standings')
    const tables = await screen.findAllByRole('table')
    expect(tables).toHaveLength(8)
    for (const t of tables) {
      expect(within(t).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Team', 'W-L-T', 'Div', 'Conf', 'PF', 'PA', 'Left'])
      expect(within(t).getAllByRole('row')).toHaveLength(5)
    }
  })

  it('Games: next week first, a swing in words, links to game pages, no zero for a game without swings', async () => {
    renderRoute('/league?tab=games')
    const week = Math.min(...league.games.map((g) => g.week))
    const section = await screen.findByRole('region', { name: `Week ${week} games` })
    const rows = within(section).getAllByRole('listitem').filter((li) => li.querySelector('a'))
    const expectIds = league.games.filter((g) => g.week === week).sort((a, b) => b.leverage_total - a.leverage_total || a.game_id.localeCompare(b.game_id)).map((g) => g.game_id)
    expect(rows.map((r) => r.querySelector('a')!.getAttribute('href'))).toEqual(expectIds.map((id) => `/game/${id}`))
    expect(section.textContent).toMatch(/[A-Z]{2,3} \d+% → \d+% (with a win|if [A-Z]{2,3} wins)/)
    const quiet = league.games.find((g) => g.swings.length === 0 && g.week === week)!
    const li = screen.getByRole('link', { name: `${quiet.away} @ ${quiet.home}` }).closest('li')!
    expect(li).toHaveTextContent(/Little here changes/)
    expect(li.textContent).not.toMatch(/→|\b0\b/)
    const later = screen.getByRole('region', { name: 'Later games' })
    expect(within(later).getAllByRole('link').length).toBeLessThanOrEqual(LATER_GAMES)
  })

  it('Odds: a sparkline for each team with two or more points, labelled with the first and last value, in the view shown', async () => {
    const withHistory = (view: string) => `/league?tab=odds&view=${view}`
    renderRoute(withHistory('student'))
    const list = await screen.findByRole('list', { name: 'AFC playoff odds' })
    const sparks = within(list).getAllByRole('img')
    const names = Object.keys(league.history).filter((t) => league.teams.find((x) => x.team === t)!.conf === 'AFC')
    expect(sparks).toHaveLength(names.length)
    const kc = list.querySelector('[data-team="KC"] svg')!
    const h = league.history.KC
    expect(kc.getAttribute('aria-label')).toMatch(new RegExp(`^Chance of the playoffs by week: Week ${h[0].week} \\d+%, Week ${h[2].week} (>99\\.9%|\\d+%)$`))
    expect(kc.getAttribute('aria-label')).not.toMatch(/(^|[^.\d])(0|100)%/)
    expect(kc.querySelectorAll('polyline')).toHaveLength(1)
    cleanup()
    renderRoute(withHistory('market'))
    const market = await screen.findByRole('list', { name: 'AFC playoff odds' })
    expect(market.querySelector('[data-team="KC"] svg')!.getAttribute('aria-label')).not.toBe(kc.getAttribute('aria-label'))
    expect(screen.getByText(/Small line: chance at each Tuesday refresh/)).toBeInTheDocument()
  })

  it('Odds: with no history, or one point, nothing is drawn and the row has no extra element', async () => {
    const lone = { ...league.history, KC: [league.history.KC[0]] }
    for (const history of [{}, lone]) {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-hist-'))
      fs.cpSync(FIX, root, { recursive: true })
      const f = JSON.parse(fs.readFileSync(path.join(root, 'site/league.json'), 'utf8'))
      f.history = history === lone ? Object.fromEntries(Object.entries(history).filter(([k]) => k === 'KC')) : history
      fs.writeFileSync(path.join(root, 'site/league.json'), JSON.stringify(f))
      const { unmount } = renderRoute('/league?tab=odds', root)
      const list = await screen.findByRole('list', { name: 'AFC playoff odds' })
      expect(within(list).queryAllByRole('img')).toHaveLength(0)
      expect(list.querySelectorAll('svg')).toHaveLength(0)
      expect(screen.queryByText(/The small line is/)).toBeNull()
      unmount()
      fs.rmSync(root, { recursive: true, force: true })
    }
  })

  it('Odds: says when it was simulated', async () => {
    renderRoute('/league?tab=odds')
    expect(await screen.findByText(/^Simulated \w{3}, /)).toBeInTheDocument()
  })

  it('Odds: says so plainly once the regular season is over, and Games has nothing to list', () => {
    const over = { ...league, games: [], odds: { student: { sources: {}, teams: {} }, market: { sources: {}, teams: {} } } }
    render(<MemoryRouter><Odds file={over} /></MemoryRouter>)
    expect(screen.getByText(/regular season is over/)).toBeInTheDocument()
    render(<MemoryRouter><Games file={over} /></MemoryRouter>)
    expect(screen.getByText(/No games are left/)).toBeInTheDocument()
  })

  it('Market view says most of it is an estimate; the Student view does not', async () => {
    renderRoute('/league?tab=odds&view=market')
    expect(await screen.findByText(/games left have a betting line yet/)).toBeInTheDocument()
    cleanup()
    renderRoute('/league?tab=odds')
    await screen.findByRole('list', { name: 'AFC playoff odds' })
    expect(screen.queryByText(/games left have a betting line yet/)).toBeNull()
  })

  it('a missing league.json shows the empty state on the playoff tabs and no strip, while Teams works', async () => {
    const root = withoutLeague()
    for (const tab of ['odds', 'standings', 'games']) {
      const { unmount } = renderRoute(`/league?tab=${tab}`, root)
      expect(await screen.findByText(/appear after the next data update/)).toBeInTheDocument()
      expect(screen.queryByRole('group', { name: 'League summary' })).toBeNull()
      expect(screen.queryByRole('alert')).toBeNull()
      unmount()
    }
    renderRoute('/league?tab=teams', root)
    expect(await screen.findByRole('group', { name: 'Starting views' })).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'League summary' })).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })
})

describe('League page', () => {
  it('renders the Teams tab from teams.json and names the page', async () => {
    renderRoute('/league?tab=teams')
    expect(await screen.findByRole('tab', { name: 'Team charts' })).toHaveAttribute('aria-selected', 'true')
    expect(document.title).toMatch(/^League/)
  })

  it('is in the nav, after This week', async () => {
    renderRoute('/league')
    const nav = await screen.findByRole('navigation')
    const links = within(nav).getAllByRole('link').map((a) => a.textContent)
    expect(links.indexOf('League')).toBe(links.indexOf('This week') + 1)
  })

  it('shows a plain card, not an error, before the file exists', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-'))
    fs.mkdirSync(path.join(root, 'site'))
    renderRoute('/league', root)
    expect(await screen.findByText(/appear after the next data update/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
