import { beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { BettingWeek } from '../../data/contract'
import { ThisWeek } from './ThisWeek'
import userEvent from '@testing-library/user-event'
import { resetBankrollCache } from '../../lib/bankroll'
import { BETS_KEY, getBets, resetBetsCache, type BetEntry } from '../../lib/betLog'
import { renderRoute } from '../../test/render'

beforeEach(() => {
  localStorage.clear()
  resetBetsCache()
  resetBankrollCache()
})

describe('Betting math, on the Method page', () => {
  it('is a tab after How it works, with the short answers and every section stacked', async () => {
    renderRoute('/method?tab=betting')
    const tabs = await screen.findAllByRole('tab', {}, { timeout: 15000 })
    expect(tabs.map((t) => t.textContent)).toEqual(['How it works', 'Betting math', 'Limits and mistakes', 'Data'])
    expect(await screen.findByRole('heading', { level: 3, name: 'Which bets are worth making?' })).toBeInTheDocument()
    // one-line answers: the ranking's out-of-sample return, and the underdog spot's own numbers
    expect(screen.getByText(/The week's five best by history; still about the cut out of sample \(\+1\.5%\)/)).toBeInTheDocument()
    expect(screen.getByText(/\+7\.2% on 368 bets since 2006, −8\.3% in 2021–2025/)).toBeInTheDocument()
  })

  it('cites the model audit with the limit from the data', async () => {
    renderRoute('/method?tab=betting')
    expect(await screen.findByText(/disagrees by 6 points or more/)).toBeInTheDocument()
    expect(screen.getByText(/backs small leans and stays away from big ones/)).toBeInTheDocument()
  })

  it('stakes: switching bets a week changes the rows', async () => {
    const user = userEvent.setup()
    renderRoute('/method?tab=betting')
    const rule = await screen.findByRole('row', { name: /Flat 1% of the starting bankroll/ })
    const six = rule.textContent
    await user.click(screen.getByRole('radio', { name: '3 bets a week' }))
    expect(screen.getByRole('row', { name: /Flat 1% of the starting bankroll/ }).textContent).not.toEqual(six)
  })

  it('lists the price bands, the fee table and the Texas box with its links', async () => {
    renderRoute('/method?tab=betting')
    expect(await screen.findByRole('group', { name: /Heavy favorite \(−400 or shorter\): −1\.3%/ })).toBeInTheDocument()
    expect(screen.getByText("The Student's leans of 5+ points")).toBeInTheDocument()
    expect(screen.getByText('Betting from Texas (not legal advice)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Texas Tribune, 2026-05-01' })).toHaveAttribute('href', 'https://www.texastribune.org/')
    expect(screen.queryByText(/Shopping for the best price/)).toBeNull()
    expect(screen.getByText('Passes')).toBeInTheDocument()
  })

  it('keeps the help line in the fine print and links the weekly page only when it is listed', async () => {
    vi.stubEnv('DEV', false)
    renderRoute('/method?tab=betting')
    expect(await screen.findByText(/1-800-MY-RESET \(1-800-697-3738\)/)).toBeInTheDocument()
    expect(screen.getByText(/No edge shown in 20 seasons/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /this week.s bets/i })).toBeNull() // card is unlisted in production
    vi.unstubAllEnvs()
  })
})

const seeded = (o: Partial<BetEntry> = {}): BetEntry => ({
  id: 'seed', game_id: '2026_10_WAS_NYG', market: 'ml', side: 'away', line: null, price: 150, stake: 10, fee: 0, venue: 'Kalshi', placed_at: '2026-11-12T12:00:00Z', ...o,
})

describe("This week's bets page", () => {
  const targetCards = async () => {
    const heads = await screen.findAllByRole('heading', { level: 3 }, { timeout: 15000 })
    return heads.map((h) => h.closest('li')!)
  }

  it('opens on the summary strip, the house rules, then targets, stay away and the slate', async () => {
    renderRoute('/betting')
    expect(await screen.findByRole('heading', { level: 1, name: "This week's bets" }, { timeout: 15000 })).toBeInTheDocument()
    const heads = (await screen.findAllByRole('heading', { level: 2 })).map((h) => h.textContent?.replace(/What is this\?$/, ''))
    expect(heads).toEqual(['Targets', 'Stay away', 'The slate'])
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['This week', 'Your bets', 'Track record'])
    const strip = screen.getByRole('group', { name: 'Summary' })
    expect(within(strip).getByText('Targets').closest('div')).toHaveTextContent('5')
    expect(within(strip).getByLabelText('Your bankroll')).toBeInTheDocument()
    expect(within(strip).getByText('1% of your bankroll')).toBeInTheDocument()
  })

  it('shows the four house rules as chips', async () => {
    renderRoute('/betting')
    const rules = await screen.findByRole('list', { name: 'House rules' }, { timeout: 15000 })
    const items = within(rules).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toHaveLength(4)
    expect(items[0]).toMatch(/Singles/)
    expect(items[1]).toMatch(/1% a bet/)
    expect(items[2]).toMatch(/Price shown or better/)
    expect(items[3]).toMatch(/No −120 to −185, no long shots/)
    expect(within(rules).getAllByRole('button', { name: 'What is this?' })).toHaveLength(4)
  })

  it('ranks five targets, each with a grade badge and a chance bar', async () => {
    renderRoute('/betting')
    const cards = await targetCards()
    expect(cards).toHaveLength(5)
    expect(cards.map((c) => within(c).getByRole('heading', { level: 3 }).textContent?.split(' ')[0])).toEqual(['MIN', 'DAL', 'KC', 'BUF', 'DEN'])
    for (const c of cards) {
      expect(within(c).getByRole('img', { name: /^Grade [ABC]$/ })).toBeInTheDocument()
      expect(within(c).getByRole('img', { name: /^Market \d+%, Student \d+%$/ })).toBeInTheDocument()
    }
    const min = cards[0]
    expect(within(min).getByRole('img', { name: 'Grade B' })).toBeInTheDocument()
    expect(within(min).getByRole('img', { name: 'Market 39%, Student 40%' })).toBeInTheDocument()
    expect(within(min).getByText('Underdog, Student agrees')).toBeInTheDocument()
    // the price now as exchange cents (+145 -> 41¢), no "too short" badge on a target
    expect(within(min).getByText(/about 41¢ on an exchange/)).toBeInTheDocument()
    expect(within(min).queryByText(/too short/)).toBeNull()
    expect(within(min).getByText('+145')).toBeInTheDocument()
    expect(within(min).getByText('#1')).toBeInTheDocument()
  })

  it('keeps the explanations in tooltips: the grade says how bets like it did, the label carries the reason', async () => {
    renderRoute('/betting')
    const dal = (await targetCards())[1]
    const tips = within(dal).getAllByRole('tooltip', { hidden: true }).map((t) => t.textContent)
    expect(tips).toContain('How bets like this have done since 2006: lost 1.6% a bet over 308 bets.')
    expect(tips).toContain('Bets like this lost 1.6% a bet since 2006 (308 bets).')
    expect(within(dal).queryByText(/Stake:/)).toBeNull()
  })

  it('stay away: chips with the reason as the accessible description, and no sentences on the face', async () => {
    renderRoute('/betting')
    const stay = (await screen.findByRole('heading', { level: 2, name: /^Stay away/ }, { timeout: 15000 })).closest('section')!
    const chip = within(stay).getAllByRole('listitem').find((li) => li.textContent?.startsWith('CAR'))!
    expect(chip).toHaveTextContent(/CAR −\d+ · Pricey favorite/)
    expect(chip.querySelector('[aria-describedby]')).toHaveAccessibleDescription(/^.+\.$/)
    expect(within(stay).getByText(/DET/)).toBeInTheDocument()
    expect(within(stay).getAllByRole('listitem').length).toBeGreaterThan(2)
  })

  it('the slate has one row per game with a split bar and pills for target and avoid', async () => {
    renderRoute('/betting')
    const slate = (await screen.findByRole('heading', { level: 2, name: 'The slate' }, { timeout: 15000 })).closest('section')!
    const rows = within(slate).getAllByRole('listitem')
    expect(rows).toHaveLength(13)
    expect(within(slate).getAllByRole('img', { name: /^Home win chance: market \d+%, Student \d+%$/ })).toHaveLength(13)
    expect(within(slate).getAllByText('target')).toHaveLength(5)
    expect(within(slate).getAllByText('skip').length).toBeGreaterThan(3)
    const dal = within(slate).getByRole('listitem', { name: 'TEN at DAL' })
    expect(within(dal).getByRole('img')).toHaveAccessibleName('Home win chance: market 77%, Student 80%')
    expect(within(slate).getByText(/Each team's win chance by the betting market/)).toBeInTheDocument()
    expect(within(slate).getByText(/Where the Student would split it/)).toBeInTheDocument()
    expect(within(dal).getByText('77%')).toBeInTheDocument()
  })

  it.each([0, 2])('shows %i targets gracefully', async (keep) => {
    const w = BettingWeek.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../../test/fixtures/site/betting_week.json'), 'utf8')))
    let n = 0
    for (const g of w.card.games) for (const x of g.sides) if (x.view === 'target' && n++ >= keep) x.view = 'none'
    const router = createMemoryRouter([{ path: '/', element: <ThisWeek w={w} bankroll={null} /> }])
    render(<RouterProvider router={router} />)
    expect(within(screen.getByRole('group', { name: 'Summary' })).getByText('Targets').closest('div')).toHaveTextContent(String(keep))
    if (keep === 0) expect(await screen.findByText(/Nothing clears the bar this week/)).toBeInTheDocument()
    else expect(screen.getAllByRole('img', { name: /^Grade/ })).toHaveLength(keep)
  })

  it('names no sportsbook', async () => {
    renderRoute('/betting')
    await targetCards()
    expect(document.body.textContent).not.toMatch(/DraftKings|FanDuel|BetMGM|BetRivers|Caesars/)
  })

  it('redirects /betting/week to /betting, keeping the tab', async () => {
    renderRoute('/betting/week?tab=record')
    expect(await screen.findByRole('heading', { level: 1, name: "This week's bets" })).toBeInTheDocument()
    expect(await screen.findByText('This season at the locks', {}, { timeout: 15000 })).toBeInTheDocument()
  })

  it('works a stake out of a typed bankroll and keeps it', async () => {
    const user = userEvent.setup()
    renderRoute('/betting')
    await user.type(await screen.findByLabelText('Your bankroll', {}, { timeout: 15000 }), '2000')
    const dal = (await targetCards())[1]
    expect(within(dal).getByText('$20 → wins $5')).toBeInTheDocument() // 20 × 100/400
    expect(screen.getByText('$20 a bet')).toBeInTheDocument()
    expect(localStorage.getItem('nfl-bankroll-v1')).toBe('2000')
  })

  it('logs a bet from a target: prefilled, added, open until the game is played', async () => {
    const user = userEvent.setup()
    renderRoute('/betting')
    await user.type(await screen.findByLabelText('Your bankroll', {}, { timeout: 15000 }), '1000')
    const dal = (await targetCards())[1]
    await user.click(within(dal).getByRole('button', { name: 'Log bet' }))
    const form = await screen.findByRole('form', { name: 'Log a bet' })
    expect(within(form).getByLabelText('Price')).toHaveValue('-400')
    expect(within(form).getByLabelText('Stake ($)')).toHaveValue('10')
    expect(within(form).getByLabelText('Game')).toHaveDisplayValue(/TEN @ DAL/)
    await user.click(within(form).getByRole('button', { name: 'Add to my log' }))
    const table = (await screen.findByRole('columnheader', { name: 'Game' })).closest('table')!
    expect(within(table).getByText('DAL to win')).toBeInTheDocument()
    expect(within(table).getByText('Open')).toBeInTheDocument()
    expect(getBets()[0]).toMatchObject({ game_id: '2026_11_TEN_DAL', market: 'ml', side: 'home', price: -400, stake: 10 })
  })

  it('refuses a price inside ±100 and a missing stake', async () => {
    const user = userEvent.setup()
    renderRoute('/betting?tab=log')
    const form = await screen.findByRole('form', { name: 'Log a bet' })
    await user.type(within(form).getByLabelText('Price'), '50')
    await user.type(within(form).getByLabelText('Stake ($)'), '10')
    await user.click(within(form).getByRole('button', { name: 'Add to my log' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/American price/)
    expect(getBets()).toHaveLength(0)
  })

  it('takes a price in cents and stores it as American', async () => {
    const user = userEvent.setup()
    renderRoute('/betting?tab=log')
    const form = await screen.findByRole('form', { name: 'Log a bet' })
    await user.click(within(form).getByRole('radio', { name: 'Cents' }))
    await user.type(within(form).getByLabelText('Price'), '80')
    expect(within(form).getByText('= −400')).toBeInTheDocument()
    await user.type(within(form).getByLabelText('Stake ($)'), '5')
    await user.click(within(form).getByRole('button', { name: 'Add to my log' }))
    await waitFor(() => expect(getBets()).toHaveLength(1))
    expect(getBets()[0].price).toBe(-400)
  })

  it('grades a logged bet against the closing map: result, profit, closing-line value, season total', async () => {
    localStorage.setItem(BETS_KEY, JSON.stringify([seeded()]))
    renderRoute('/betting?tab=log')
    const table = (await screen.findByRole('columnheader', { name: 'Game' })).closest('table')!
    const row = within(table).getByText('WAS to win').closest('tr')!
    expect(within(row).getByText('Won')).toBeInTheDocument()
    expect(within(row).getByText('+$15.00')).toBeInTheDocument()
    expect(within(row).getByText('+7.6 pts')).toBeInTheDocument()
    expect(within(row).getByText('+150')).toBeInTheDocument()
    expect(screen.getByText("The card's paper record at the locks")).toBeInTheDocument()
  })

  it('deletes a bet', async () => {
    const user = userEvent.setup()
    localStorage.setItem(BETS_KEY, JSON.stringify([seeded()]))
    renderRoute('/betting?tab=log')
    await user.click(await screen.findByRole('button', { name: 'Delete WAS to win' }))
    expect(await screen.findByText('No bets logged yet.')).toBeInTheDocument()
    expect(getBets()).toHaveLength(0)
  })

  it('exports CSV and JSON downloads of the log', async () => {
    const user = userEvent.setup()
    localStorage.setItem(BETS_KEY, JSON.stringify([seeded()]))
    const blobs: Blob[] = []
    URL.createObjectURL = vi.fn((b: Blob | MediaSource) => {
      blobs.push(b as Blob)
      return 'blob:test'
    })
    URL.revokeObjectURL = vi.fn()
    const names: string[] = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download)
    })
    renderRoute('/betting?tab=log')
    await user.click(await screen.findByRole('button', { name: 'Export CSV' }))
    await user.click(screen.getByRole('button', { name: 'Export JSON' }))
    expect(names[0]).toMatch(/^nfl-bets-\d{4}-\d{2}-\d{2}\.csv$/)
    expect(names[1]).toMatch(/^nfl-bets-\d{4}-\d{2}-\d{2}\.json$/)
    expect(blobs[0].type).toBe('text/csv')
    expect(await blobs[0].text()).toContain('seed,2026_10_WAS_NYG,ml,away,,150,10,0,Kalshi')
    expect(JSON.parse(await blobs[1].text())).toEqual([expect.objectContaining({ id: 'seed', price: 150 })])
    click.mockRestore()
  })

  it('imports a JSON file, merging by id and counting what it skipped', async () => {
    const user = userEvent.setup()
    renderRoute('/betting?tab=log')
    const input = (await screen.findByText('Import JSON')).querySelector('input')!
    const file = new File([JSON.stringify([seeded({ id: 'imp' }), { id: 'bad' }])], 'bets.json', { type: 'application/json' })
    await user.upload(input, file)
    expect(await screen.findByText(/Imported 1 new bet; skipped 1 that couldn’t be read\./)).toBeInTheDocument()
    expect(getBets().map((e) => e.id)).toEqual(['imp'])
  })

  it('track record tab: the return chart, the live record, and the numbers behind it', async () => {
    const user = userEvent.setup()
    renderRoute('/betting?tab=record')
    const chart = await screen.findByRole('img', { name: /^Return per bet\./ }, { timeout: 15000 })
    expect(chart).toHaveAccessibleName(/Targets: \+1\.5% in history, −3\.5% this season/)
    expect(chart).toHaveAccessibleName(/Stay away: −5\.5% in history, −35\.4% this season/)
    expect(screen.getByText('History (re-ranked each season)')).toBeInTheDocument()
    expect(screen.getByText('2026 at our locks')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Targets' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Avoids' })).toBeInTheDocument()
    await user.click(screen.getByText('Show the numbers'))
    expect(screen.getByRole('row', { name: /Targets \(re-ranked each season\) 1,305/ })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /The Student's pick everywhere/ })).toBeInTheDocument()
  })
})
