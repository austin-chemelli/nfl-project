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

  it('Odds: both conferences on one page, the market by default, the Student a click away, one rule after the 7th row', async () => {
    renderRoute('/league?tab=odds&layout=table')
    const order = (conf: string, v: 'market' | 'student') =>
      league.teams.filter((t) => t.conf === conf).map((t) => t.team).sort((a, b) => league.odds[v].teams[b].playoffs - league.odds[v].teams[a].playoffs || a.localeCompare(b))
    const list = await screen.findByRole('list', { name: 'AFC playoff odds' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(16)
    expect(rows.map((r) => r.getAttribute('data-team'))).toEqual(order('AFC', 'market'))
    expect(rows.filter((r) => r.className.includes('border-t-2'))).toHaveLength(1)
    expect(rows[7].className).toContain('border-t-2')
    expect(within(screen.getByRole('list', { name: 'NFC playoff odds' })).getAllByRole('listitem').map((r) => r.getAttribute('data-team'))).toEqual(order('NFC', 'market'))
    expect(screen.queryByRole('radiogroup', { name: 'Conference' })).toBeNull()
    expect(screen.getByRole('radio', { name: 'Market' })).toHaveAttribute('aria-checked', 'true')

    await userEvent.click(screen.getByRole('radio', { name: 'Student' }))
    const nfc = within(await screen.findByRole('list', { name: 'NFC playoff odds' })).getAllByRole('listitem')
    expect(nfc.map((r) => r.getAttribute('data-team'))).toEqual(order('NFC', 'student'))
    expect(screen.getByRole('radio', { name: 'Student' })).toHaveAttribute('aria-checked', 'true')
  })

  it('Odds: the projected bracket is the default, with both conferences, the Super Bowl and the table a click away', async () => {
    renderRoute('/league?tab=odds')
    const afc = await screen.findByRole('region', { name: 'AFC projected bracket' })
    expect(screen.getByRole('region', { name: 'NFC projected bracket' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Bracket' })).toHaveAttribute('aria-checked', 'true')
    // seven seeds: one bye and three wild-card games, then two divisional games and a conference game
    expect(within(afc).getByText('Bye')).toBeInTheDocument()
    expect(afc.querySelectorAll('[data-team]')).toHaveLength(1 + 6 + 4 + 2)
    expect(within(screen.getByRole('region', { name: 'Projected Super Bowl' })).getByText(/Champion:/)).toBeInTheDocument()
    // each team in the bracket shows its record and its projected final record
    const first = afc.querySelector('[data-team]') as HTMLElement
    expect(first.textContent).toMatch(/\d+–\d+ · proj \d+–\d+/)
    await userEvent.click(screen.getByRole('radio', { name: 'Table' }))
    expect(await screen.findByRole('list', { name: 'AFC playoff odds' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'AFC projected bracket' })).toBeNull()
  })

  it('Odds: restores the toggles from the URL', async () => {
    renderRoute('/league?tab=odds&layout=table&view=student')
    await screen.findByRole('list', { name: 'NFC playoff odds' })
    expect(screen.getByRole('radio', { name: 'Student' })).toHaveAttribute('aria-checked', 'true')
  })

  it('Odds: team bars use the team color slot, not a raw color, and no probability reads 0% or 100%', async () => {
    const { container } = renderRoute('/league?tab=odds&layout=table')
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
    renderRoute('/league?tab=odds&layout=table')
    const row = within(await screen.findByRole('list', { name: 'AFC playoff odds' })).getAllByRole('listitem')[0]
    await userEvent.hover(row)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Win the Super Bowl')
  })

  it('Odds: one fine print block, with the file\'s counts and how the estimate tested', async () => {
    renderRoute('/league?tab=odds&layout=table')
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
    const withHistory = (view: string) => `/league?tab=odds&layout=table&view=${view}`
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
      const { unmount } = renderRoute('/league?tab=odds&layout=table', root)
      const list = await screen.findByRole('list', { name: 'AFC playoff odds' })
      expect(within(list).queryAllByRole('img')).toHaveLength(0)
      expect(list.querySelectorAll('svg')).toHaveLength(0)
      expect(screen.queryByText(/The small line is/)).toBeNull()
      unmount()
      fs.rmSync(root, { recursive: true, force: true })
    }
  })

  it('Odds: says when it was simulated', async () => {
    renderRoute('/league?tab=odds&layout=table')
    expect(await screen.findByText(/^Simulated \w{3}, /)).toBeInTheDocument()
  })

  it('Odds: says so plainly once the regular season is over, and Games has nothing to list', () => {
    const over = { ...league, games: [], odds: { student: { sources: {}, teams: {}, ratings: {}, home_term: 0 }, market: { sources: {}, teams: {}, ratings: {}, home_term: 0 } } }
    render(<MemoryRouter><Odds file={over} /></MemoryRouter>)
    expect(screen.getByText(/regular season is over/)).toBeInTheDocument()
    render(<MemoryRouter><Games file={over} /></MemoryRouter>)
    expect(screen.getByText(/No games are left/)).toBeInTheDocument()
  })

  it('Market view says most of it is an estimate; the Student view does not', async () => {
    renderRoute('/league?tab=odds&layout=table')
    expect(await screen.findByText(/games left have a betting line yet/)).toBeInTheDocument()
    cleanup()
    renderRoute('/league?tab=odds&layout=table&view=student')
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

describe('What if mode (M26.4)', () => {
  const ratings = Object.fromEntries(league.teams.map((t, i) => [t.team, ((i * 7) % 32 - 15.5) / 18]))
  const ready: LeagueFile = {
    ...league,
    through_week: 0,
    played: [],
    odds: { student: { ...league.odds.student, ratings, home_term: 0.15 }, market: { ...league.odds.market, ratings, home_term: 0.15 } },
  }
  const runs = { quick: 100, full: 200 }

  it('has no switch on a file from before M26.2', () => {
    render(<MemoryRouter><Odds file={league} runs={runs} /></MemoryRouter>)
    expect(screen.queryByRole('radiogroup', { name: 'What if' })).toBeNull()
  })

  it('turns on, decides a game, and shows now → what if', async () => {
    render(<MemoryRouter initialEntries={['/league?whatif=1&layout=table']}><Odds file={ready} runs={runs} /></MemoryRouter>)
    expect(screen.getByRole('radio', { name: 'What if…' })).toHaveAttribute('aria-checked', 'true')
    const panel = screen.getByRole('region', { name: 'What if: decide games' })
    expect(await screen.findByText(/200 simulated seasons/)).toBeInTheDocument()
    expect(screen.getByText('Decide a game to see who it moves.')).toBeInTheDocument()
    const game = within(panel).getAllByRole('group', { name: /^Decide / })[0]
    const away = within(game).getAllByRole('button')[0]
    await userEvent.click(away)
    expect(away).toHaveAttribute('aria-pressed', 'true')
    expect(within(panel).getByText(/1 of 34 decided/)).toBeInTheDocument()
    expect(await screen.findByText(/Your scenario, not the published odds · 200 simulated seasons/)).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Favorites win out' }))
    expect(within(panel).getByText(/34 of 34 decided/)).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Reset' }))
    expect(within(panel).getByText(/0 of 34 decided/)).toBeInTheDocument()
  })

  it('by team: one team wins out, then clears', async () => {
    render(<MemoryRouter initialEntries={['/league?whatif=1&layout=table']}><Odds file={ready} runs={runs} /></MemoryRouter>)
    const panel = screen.getByRole('region', { name: 'What if: decide games' })
    await userEvent.click(within(panel).getByRole('radio', { name: 'By team' }))
    const team = ready.games[0].home
    await userEvent.selectOptions(within(panel).getByRole('combobox', { name: 'Team' }), team)
    const n = ready.games.filter((g) => g.home === team || g.away === team).length
    expect(within(panel).getAllByRole('group', { name: /^Decide / })).toHaveLength(n)
    await userEvent.click(within(panel).getByRole('button', { name: `${team} wins out` }))
    expect(within(panel).getByText(new RegExp(`decided ${n}–0 for ${team}`))).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Clear' }))
    expect(within(panel).getByText(new RegExp(`decided 0–0 for ${team}`))).toBeInTheDocument()
  })
})
