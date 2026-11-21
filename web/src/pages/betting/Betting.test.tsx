import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
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
    expect(screen.getByText(/7\.2% on 368 bets/)).toBeInTheDocument()
    // on the wave-3 Student the underdog spot fails the bar: the copy says so
    expect(screen.getByText(/Nothing for sure/)).toBeInTheDocument()
    expect(screen.getByText(/doesn.t clear our bar for a real edge/)).toBeInTheDocument()
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
  it('opens on the strategy box, then targets, stay away and the slate', async () => {
    renderRoute('/betting')
    expect(await screen.findByRole('heading', { level: 1, name: "This week's bets" })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 3, name: 'How to call your shot' })).toBeInTheDocument()
    expect(await screen.findByText(/The best spot is an underdog at \+120 to \+185: \+7\.2% on 368 bets since 2006/)).toBeInTheDocument()
    expect(screen.getByText(/in 2021-2025/)).toBeInTheDocument()
    const heads = (await screen.findAllByRole('heading', { level: 2 })).map((h) => h.textContent)
    expect(heads.map((h) => h?.split('?')[0])).toEqual(['Targeted bets', 'Stay away', 'The whole slate'])
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent)
    expect(tabs).toEqual(['This week', 'Your bets', 'Track record'])
  })

  it('shows a target with its price, the price needed and what it would stake', async () => {
    renderRoute('/betting')
    const dal = (await screen.findByRole('heading', { level: 3, name: 'DAL to beat TEN' })).closest('div')!.parentElement!
    expect(within(dal).getByText('Price too short')).toBeInTheDocument()
    expect(within(dal).getByText('Only at −331 or better')).toBeInTheDocument()
    expect(within(dal).getByText(/on an exchange, 75¢ or less/)).toBeInTheDocument()
    expect(within(dal).getByText(/Student 80% · market 77%/)).toBeInTheDocument()
    expect(within(dal).getByText(/Stake: 1% of your bankroll/)).toBeInTheDocument()
    expect(within(dal).queryByText('Best spot')).toBeNull()
  })

  it('stay away lists tempting sides with their reason, and the slate lists every game with tags', async () => {
    renderRoute('/betting')
    const stay = (await screen.findByRole('heading', { level: 2, name: /^Stay away/ })).closest('section')!
    expect(within(stay).getByText('CAR')).toBeInTheDocument()
    expect(within(stay).getByText('DET')).toBeInTheDocument()
    const slate = screen.getByRole('heading', { level: 2, name: 'The whole slate' }).closest('section')!
    expect(within(slate).getAllByRole('row')).toHaveLength(14) // header + 13 games
    expect(within(slate).getAllByText('Target')).toHaveLength(1)
    expect(within(slate).getAllByText('Avoid').length).toBeGreaterThan(3)
    expect(within(slate).getByText(/Untagged sides cost about the cut \(−1\.3%\)/)).toBeInTheDocument()
  })

  it('names no sportsbook', async () => {
    renderRoute('/betting')
    await screen.findByRole('heading', { level: 3, name: 'How to call your shot' })
    expect(document.body.textContent).not.toMatch(/DraftKings|FanDuel|BetMGM|BetRivers|Caesars/)
  })

  it('redirects /betting/week to /betting, keeping the tab', async () => {
    renderRoute('/betting/week?tab=record')
    expect(await screen.findByRole('heading', { level: 1, name: "This week's bets" })).toBeInTheDocument()
    expect(await screen.findByText('This season at the locks')).toBeInTheDocument()
  })

  it('works a stake out of a typed bankroll and keeps it', async () => {
    const user = userEvent.setup()
    renderRoute('/betting')
    await user.type(await screen.findByLabelText('Your bankroll'), '2000')
    const dal = screen.getByRole('heading', { level: 3, name: 'DAL to beat TEN' }).closest('div')!.parentElement!
    expect(within(dal).getByText(/Stake: \$20 to win \$5\.00/)).toBeInTheDocument() // 20 × 100/400
    expect(localStorage.getItem('nfl-bankroll-v1')).toBe('2000')
  })

  it('logs a bet from a target: prefilled, added, open until the game is played', async () => {
    const user = userEvent.setup()
    renderRoute('/betting')
    await user.type(await screen.findByLabelText('Your bankroll'), '1000')
    const dal = screen.getByRole('heading', { level: 3, name: 'DAL to beat TEN' }).closest('div')!.parentElement!
    await user.click(within(dal).getByRole('button', { name: 'Log this bet' }))
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

  it('track record tab: targets against avoids, and the rules in history', async () => {
    renderRoute('/betting?tab=record')
    expect(await screen.findByText('Targets against avoids, one unit a bet at the consensus price at each lock.')).toBeInTheDocument()
    expect(screen.getByText('Targets')).toBeInTheDocument()
    expect(screen.getByText('Avoids')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Underdog lean 368/ })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /The Student's pick everywhere/ })).toBeInTheDocument()
  })
})
