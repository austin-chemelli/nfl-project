import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { LeagueFile } from '../../data/contract'
import { renderRoute } from '../../test/render'
import { defaultSimilarTeam } from './context'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures')
const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'site/league.json'), 'utf8')))

afterEach(cleanup)

const open = async (url = '/league?tab=similar') => {
  renderRoute(url)
  return screen.findByRole('list', { name: /^Seasons most like/ })
}

/** The fixtures with league.json's similar changed. */
function withSimilar(similar: unknown): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-sim-'))
  fs.cpSync(FIX, root, { recursive: true })
  const f = JSON.parse(fs.readFileSync(path.join(root, 'site/league.json'), 'utf8'))
  if (similar === undefined) delete f.similar
  else f.similar = similar
  fs.writeFileSync(path.join(root, 'site/league.json'), JSON.stringify(f))
  return root
}

describe('Similar seasons tab', () => {
  it('is the fifth tab, after Games that matter', async () => {
    renderRoute('/league')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['Playoff odds', 'Teams', 'Standings', 'Games that matter', 'Similar seasons'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('opens on the default team: a lede that describes, a tile row and ten rows', async () => {
    const list = await open()
    const code = defaultSimilarTeam(league)!
    expect(screen.getByLabelText('Team')).toHaveValue(code)
    expect(within(list).getAllByRole('listitem')).toHaveLength(10)
    const entry = league.similar[code]
    expect(screen.getByText(new RegExp(`after ${entry.games_played} games finished like this`))).toBeInTheDocument()
    const tiles = screen.getByRole('group', { name: `The ${entry.k_summary} most similar seasons` })
    expect(tiles).toHaveTextContent(`${entry.made_playoffs} of ${entry.k_summary}`)
    expect(tiles).toHaveTextContent('Won the Super Bowl')
    expect(screen.getByRole('link', { name: 'playoff odds' })).toHaveAttribute('href', expect.stringContaining('tab=odds'))
  })

  it('prints the team as printed then, the record then and final, and the round in words', async () => {
    const list = await open('/league?tab=similar&team=CHI')
    const rows = within(list).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('2018')
    expect(rows[0]).toHaveTextContent('CAR')
    expect(rows[0]).toHaveTextContent('6–2')
    expect(rows[0]).toHaveTextContent('7–9')
    expect(rows[0]).toHaveTextContent('Missed the playoffs')
    expect(list).toHaveTextContent('SD')
    expect(list).toHaveTextContent('OAK')
    expect(list).toHaveTextContent('STL')
    expect(list).toHaveTextContent('Lost in the divisional round')
    expect(list).toHaveTextContent('Won the Super Bowl')
    expect(within(list).getByText('SD')).toHaveAttribute('title', 'Los Angeles Chargers')
  })

  it('round-trips ?team= through the picker and the URL', async () => {
    await open('/league?tab=similar&team=KC')
    expect(screen.getByLabelText('Team')).toHaveValue('KC')
    await userEvent.selectOptions(screen.getByLabelText('Team'), 'BUF')
    expect(screen.getByLabelText('Team')).toHaveValue('BUF')
    expect(screen.getByRole('tab', { name: 'Similar seasons' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/looked like Buffalo Bills after/)).toBeInTheDocument()
  })

  it('ignores an unknown ?team=', async () => {
    await open('/league?tab=similar&team=constructor')
    expect(screen.getByLabelText('Team')).toHaveValue(defaultSimilarTeam(league)!)
  })

  it('says plainly why a team with no entry has nothing', async () => {
    renderRoute('/league?tab=similar&team=NO')
    const note = await screen.findByText(/has nothing to show yet: /)
    expect(note).toHaveTextContent('New Orleans Saints has nothing to show yet')
    expect(note).toHaveTextContent('fewer than four games')
    expect(screen.queryByRole('list', { name: /^Seasons most like/ })).toBeNull()
    expect(screen.getByLabelText('Team')).toHaveValue('NO')
  })

  it('marks the teams without an entry in the picker', async () => {
    await open()
    expect(within(screen.getByLabelText('Team')).getByRole('option', { name: /New Orleans Saints \(nothing to show yet\)/ })).toBeInTheDocument()
  })

  it('never says "will": it is descriptive, and points to the playoff odds as the forecast', async () => {
    await open('/league?tab=similar&team=CHI')
    const text = document.body.textContent ?? ''
    expect(text).toMatch(/isn't a forecast/)
    expect(text).not.toMatch(/\bwill\b/i)
    expect(text).not.toMatch(/clinch|eliminat/i)
    cleanup()
    renderRoute('/league?tab=similar&team=NO')
    await screen.findByText(/has nothing to show yet: /)
    expect(document.body.textContent).not.toMatch(/\bwill\b/i)
  })

  it('has one fine print block with the years, the measures and the format change', async () => {
    await open()
    const fine = screen.getByText('How these seasons are picked').closest('details')!
    expect(fine).toHaveTextContent('2002 to 2025')
    expect(fine).toHaveTextContent('counted double')
    expect(fine).toHaveTextContent('six teams per conference')
    expect(fine).toHaveTextContent('since moved')
    expect(document.querySelectorAll('details summary')).toHaveLength(1)
  })

  it('shows a plain message, not a crash, for a file with no similar seasons', async () => {
    const root = withSimilar(undefined)
    renderRoute('/league?tab=similar', root)
    expect(await screen.findByText(/Similar seasons appear once teams have played four games/)).toBeInTheDocument()
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
