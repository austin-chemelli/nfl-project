import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { cleanup, fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { LeagueFile, SimilarFile } from '../../data/contract'
import { renderRoute } from '../../test/render'
import { defaultSimilarTeam } from './similar'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures')
const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'site/league.json'), 'utf8')))
const sim = SimilarFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'site/similar.json'), 'utf8')))

afterEach(cleanup)

const open = async (url = '/league?tab=similar') => {
  renderRoute(url)
  return screen.findByRole('list', { name: /^Seasons most like/ })
}

/** The fixtures with similar.json replaced (undefined removes it; a string is written as is) and league.json's through_week set. */
function withSimilar(similar: unknown, through?: number): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-sim-'))
  fs.cpSync(FIX, root, { recursive: true })
  const file = path.join(root, 'site/similar.json')
  if (similar === undefined) fs.rmSync(file)
  else fs.writeFileSync(file, typeof similar === 'string' ? similar : JSON.stringify(similar))
  if (through !== undefined) {
    const lp = path.join(root, 'site/league.json')
    const f = JSON.parse(fs.readFileSync(lp, 'utf8'))
    f.through_week = through
    fs.writeFileSync(lp, JSON.stringify(f))
  }
  return root
}

describe('Similar seasons tab', () => {
  it('is the fifth tab, after Games that matter', async () => {
    renderRoute('/league')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['Playoff odds', 'Teams', 'Standings', 'Games that matter', 'Similar seasons'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('opens on the default team with the grid, the cards, the chart and ten rows', async () => {
    const list = await open()
    const code = defaultSimilarTeam(league, sim)!
    expect(screen.getByLabelText('Team')).toHaveValue(code)
    expect(within(list).getAllByRole('listitem')).toHaveLength(10)
    const entry = sim.teams[code]
    expect(screen.getByText(new RegExp(`after ${entry.games_played} games finished like this`))).toBeInTheDocument()
    expect(screen.getByRole('group', { name: /nearest seasons finished/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Where the .* and their 25 nearest seasons sit/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'playoff odds' })).toHaveAttribute('href', expect.stringContaining('tab=odds'))
    expect(screen.queryByText('Reached the divisional round')).toBeNull() // the five tiles are gone
  })

  it('draws 25 squares that name their season on focus', async () => {
    await open('/league?tab=similar&team=CHI')
    const grid = screen.getByRole('group', { name: /nearest seasons finished/ })
    const squares = within(grid).getAllByRole('img')
    expect(squares).toHaveLength(25)
    fireEvent.focus(squares[0])
    expect(await screen.findByTestId('chart-tip')).toHaveTextContent(/^\d{4} [A-Z]+, \d+–\d+/)
    expect(grid.closest('section')).toHaveTextContent(/\d+ of 25 made the playoffs/)
  })

  it('shows the flag cards in the order red, looks bad, strength, with the counts', async () => {
    await open('/league?tab=similar&team=CHI')
    const groups = screen.getAllByRole('region').filter((r) => ['Red flags', "Looks bad, wasn't", 'Real strengths'].includes(r.getAttribute('aria-label') ?? ''))
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual(['Red flags', "Looks bad, wasn't", 'Real strengths'])
    expect(groups[0]).toHaveTextContent('Offense: 27th. Among past teams at 5-2, those with a bottom-quarter offense made the playoffs 11 of 28 times, against 58 of 80 for the rest.')
    expect(groups[1]).toHaveTextContent('Record undersells them.')
    expect(groups[2]).toHaveTextContent('reached a conference game 16 of 40 times')
  })

  it('hides an empty group, and says so when a team has no flags at all', async () => {
    await open('/league?tab=similar&team=KC')
    expect(screen.queryByRole('region', { name: 'Red flags' })).toBeNull()
    expect(screen.getByRole('region', { name: 'Real strengths' })).toBeInTheDocument()
    cleanup()
    await open('/league?tab=similar&team=DET')
    expect(screen.getByText(/Nothing on our list of measures stands out/)).toBeInTheDocument()
  })

  it('prints the team as printed then, the record then and final, the round in words, and closest and furthest', async () => {
    const list = await open('/league?tab=similar&team=CHI')
    const rows = within(list).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('2011')
    expect(rows[0]).toHaveTextContent('SD')
    expect(rows[0]).toHaveTextContent(/Closest on .+ · furthest on /)
    expect(list).toHaveTextContent('OAK')
    expect(within(list).getByText('SD')).toHaveAttribute('title', 'Los Angeles Chargers')
  })

  it('traces a neighbour across the chart on hover and on keyboard focus', async () => {
    const list = await open('/league?tab=similar&team=CHI')
    const rows = within(list).getAllByRole('listitem')
    const chart = screen.getByRole('img', { name: /nearest seasons sit/ })
    expect(chart.querySelectorAll('polyline')).toHaveLength(0)
    await userEvent.hover(rows[2])
    expect(chart.querySelectorAll('polyline')).toHaveLength(1)
    expect(chart.querySelectorAll('polyline')[0].getAttribute('points')!.split(' ')).toHaveLength(7)
    await userEvent.unhover(rows[2])
    expect(chart.querySelectorAll('polyline')).toHaveLength(0)
    fireEvent.focus(rows[3])
    expect(chart.querySelectorAll('polyline')).toHaveLength(1)
    expect(screen.getByText(/^20\d\d [A-Z]+, \d+–\d+/, { selector: 'span' })).toBeInTheDocument()
    fireEvent.blur(rows[3])
    expect(chart.querySelectorAll('polyline')).toHaveLength(0)
  })

  it('labels Schedule as hardest to the right, and puts the team dot in the chart', async () => {
    await open('/league?tab=similar&team=CHI')
    const chart = screen.getByRole('img', { name: /nearest seasons sit/ })
    expect(chart).toHaveTextContent('(right = hardest)')
    expect(chart.querySelectorAll('[data-row]')).toHaveLength(7)
    expect(chart.closest('[data-matchup]')).not.toBeNull()
  })

  it('round-trips ?team= through the picker and the URL', async () => {
    await open('/league?tab=similar&team=KC')
    expect(screen.getByLabelText('Team')).toHaveValue('KC')
    await userEvent.selectOptions(screen.getByLabelText('Team'), 'BUF')
    expect(screen.getByLabelText('Team')).toHaveValue('BUF')
    expect(screen.getByRole('tab', { name: 'Similar seasons' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/looked like the Buffalo Bills after/)).toBeInTheDocument()
  })

  it('ignores an unknown ?team=', async () => {
    await open('/league?tab=similar&team=constructor')
    expect(screen.getByLabelText('Team')).toHaveValue(defaultSimilarTeam(league, sim)!)
  })

  it('says plainly why a team with no entry has nothing, without the "teams that looked like" clause', async () => {
    renderRoute('/league?tab=similar&team=NO')
    const note = await screen.findByText(/has nothing to show yet: /)
    expect(note).toHaveTextContent('New Orleans Saints has nothing to show yet')
    expect(note).toHaveTextContent('fewer than four games')
    expect(screen.queryByRole('list', { name: /^Seasons most like/ })).toBeNull()
    expect(screen.getByLabelText('Team')).toHaveValue('NO')
    expect(document.body.textContent).not.toMatch(/Teams that looked like/)
    expect(document.body.textContent).toMatch(/isn't a forecast/)
  })

  it('marks the teams without an entry in the picker', async () => {
    await open()
    expect(within(screen.getByLabelText('Team')).getByRole('option', { name: /New Orleans Saints \(nothing to show yet\)/ })).toBeInTheDocument()
  })

  it('never says "will" or "clinched": it is descriptive, and points to the playoff odds as the forecast', async () => {
    for (const team of ['CHI', 'KC', 'DET', 'SF', 'NO']) {
      renderRoute(`/league?tab=similar&team=${team}`)
      await screen.findByText(/isn't a forecast/)
      await screen.findByLabelText('Team')
      // open the fine print too: its text is in the DOM either way
      const text = document.body.textContent ?? ''
      expect(text).not.toMatch(/\bwill\b/i)
      expect(text).not.toMatch(/clinch|eliminat/i)
      cleanup()
    }
  })

  it('has one fine print block with the years from the pool, the 16-game note, the flag list and the format change', async () => {
    await open()
    const fine = screen.getByText('How these seasons are picked').closest('details')!
    expect(fine).toHaveTextContent('2002 to 2025')
    expect(fine).toHaveTextContent('counted double')
    expect(fine).toHaveTextContent('12-4 and 12-5')
    expect(fine).toHaveTextContent('6, 8, 10 and 12 games')
    expect(fine).toHaveTextContent("QB play's penalty was mostly in the newer half")
    expect(fine).toHaveTextContent('six teams per conference')
    expect(fine).toHaveTextContent('since moved')
    expect(document.querySelectorAll('details summary')).toHaveLength(1)
  })

  it('reads the pool late in the season: 2021 to 2025', async () => {
    const f = JSON.parse(JSON.stringify(sim))
    for (const t of Object.values<{ pool: unknown }>(f.teams)) t.pool = { seasons: [2021, 2025], n: 160 }
    const root = withSimilar(f)
    renderRoute('/league?tab=similar&team=CHI', root)
    await screen.findByRole('list', { name: /^Seasons most like/ })
    expect(screen.getByText('How these seasons are picked').closest('details')).toHaveTextContent('2021 to 2025')
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('says the four-game thing only before four games', async () => {
    const empty = { ...sim, teams: {} }
    let root = withSimilar(empty, 3)
    renderRoute('/league?tab=similar', root)
    expect(await screen.findByText(/Similar seasons appear once teams have played four games/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    cleanup()
    fs.rmSync(root, { recursive: true, force: true })
    root = withSimilar(empty, 9)
    renderRoute('/league?tab=similar', root)
    expect(await screen.findByText("Similar seasons aren't available right now.")).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/four games/)
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('shows the not-built-yet card when similar.json is missing, and the other tabs still work', async () => {
    const root = withSimilar(undefined)
    renderRoute('/league?tab=similar', root)
    expect(await screen.findByText('Similar seasons appear after the next data update.')).toBeInTheDocument()
    cleanup()
    renderRoute('/league?tab=standings', root)
    expect(await screen.findByRole('tab', { name: 'Standings', selected: true })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('a malformed similar.json is an error on this tab only', async () => {
    const root = withSimilar('{"schema_version": "1", "teams": 5}')
    renderRoute('/league?tab=similar', root)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    cleanup()
    renderRoute('/league?tab=odds', root)
    await screen.findByRole('tab', { name: 'Playoff odds', selected: true })
    expect(screen.queryByRole('alert')).toBeNull()
    fs.rmSync(root, { recursive: true, force: true })
  })

  it('shows the missing-file card when league.json is absent', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-nolg-'))
    fs.cpSync(FIX, root, { recursive: true })
    fs.rmSync(path.join(root, 'site/league.json'))
    renderRoute('/league?tab=similar', root)
    expect(await screen.findByText('Similar seasons appear after the next data update.')).toBeInTheDocument()
    fs.rmSync(root, { recursive: true, force: true })
  })
})
