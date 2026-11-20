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

describe('Betting math page', () => {
  it('shows the four tiles, each from the file, and the short answers first', async () => {
    renderRoute('/betting')
    const strip = await screen.findByRole('group', { name: 'Betting math summary' })
    const tiles = within(strip).getAllByRole('button')
    expect(tiles).toHaveLength(4)
    expect(tiles[0]).toHaveTextContent('Singles or parlays?')
    expect(tiles[0]).toHaveTextContent('−3.6%')
    expect(tiles[0]).toHaveTextContent('4 legs: −15.6%')
    expect(tiles[1]).toHaveTextContent('Heavy favorites')
    expect(tiles[1]).toHaveTextContent('−1.3%')
    expect(tiles[2]).toHaveTextContent('−2.7%')
    expect(tiles[3]).toHaveTextContent('1%')
    expect(tiles[3]).toHaveTextContent('lost half the bankroll in 0% of seasons; 5%: 44%')
    expect(screen.getByRole('heading', { level: 3, name: 'One bet at a time, or parlays?' })).toBeInTheDocument()
    expect(screen.getByText(/one loss at −650 erases about 6\.5 wins/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Betting math')
    expect(screen.getByText(/What 20 seasons of our own lines say/)).toBeInTheDocument()
  })

  it('has the seven tabs, and a tile opens its tab', async () => {
    const user = userEvent.setup()
    renderRoute('/betting')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['Short answers', 'Prices', 'Parlays', 'How much to stake', 'Our models', 'Spreads and totals', 'Where and how'])
    await user.click(within(screen.getByRole('group', { name: 'Betting math summary' })).getByRole('button', { name: /Stake per bet/ }))
    expect(await screen.findByText('18-week seasons replayed from history at each staking rule.')).toBeInTheDocument()
  })

  it('stakes tab: switching bets a week changes the rows', async () => {
    const user = userEvent.setup()
    renderRoute('/betting?tab=stakes')
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(8) // header + 7 rules
    const six = within(table).getByRole('row', { name: /Flat 1% of the starting bankroll/ }).textContent
    await user.click(screen.getByRole('radio', { name: '3 bets a week' }))
    const three = within(screen.getByRole('table')).getByRole('row', { name: /Flat 1% of the starting bankroll/ })
    expect(three.textContent).not.toEqual(six)
  })

  it('prices tab: lists the bands with their prices and returns', async () => {
    renderRoute('/betting?tab=prices')
    expect(await screen.findByText('Every side bet at the closing moneyline, by price.')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: /Heavy favorite \(−400 or shorter\): −1\.3%/ })).toBeInTheDocument()
  })

  it('where tab: the fee table, the exchange table and the Texas box with its links', async () => {
    renderRoute('/betting?tab=where')
    expect(await screen.findByText("The Student's leans of 5+ points")).toBeInTheDocument()
    expect(screen.getByText('+373')).toBeInTheDocument()
    expect(screen.getByText('Betting from Texas (not legal advice)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Texas Tribune, 2026-05-01' })).toHaveAttribute('href', 'https://www.texastribune.org/')
  })

  it('spreads tab: the rule that passes and the one that does not', async () => {
    renderRoute('/betting?tab=spreads')
    expect(await screen.findByText('Passes')).toBeInTheDocument()
    expect(screen.getByText("Doesn't clear the bar")).toBeInTheDocument()
  })

  it('keeps the help line in the fine print', async () => {
    renderRoute('/betting')
    expect(await screen.findByText(/1-800-MY-RESET \(1-800-697-3738\)/)).toBeInTheDocument()
    expect(screen.getByText(/No edge shown in 20 seasons/)).toBeInTheDocument()
  })
})

const seeded = (o: Partial<BetEntry> = {}): BetEntry => ({
  id: 'seed', game_id: '2026_10_WAS_NYG', market: 'ml', side: 'away', line: null, price: 150, stake: 10, fee: 0, venue: 'Kalshi', placed_at: '2026-11-12T12:00:00Z', ...o,
})

describe('Your betting card page', () => {
  it('lists the worth-a-look games first, then for fun, then skip', async () => {
    renderRoute('/betting/week')
    const heads = await screen.findAllByRole('heading', { level: 2 })
    const names = heads.map((h) => h.textContent)
    expect(names.indexOf('Worth a look')).toBeLessThan(names.indexOf('For fun'))
    expect(names.indexOf('For fun')).toBeLessThan(names.indexOf('Skip'))
    expect(names.indexOf('Skip')).toBeLessThan(names.indexOf('Started'))
    const cards = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(cards.slice(0, 4)).toEqual(['BUF to win', 'DET to win', 'DAL to win', 'DEN to win'])
    expect(screen.getByText(/Singles only, no parlays\. 1% a bet\. The model version: student 280a0a3\+38b91b6e4ee1\./)).toBeInTheDocument()
    expect(screen.getByText(/No targeted spread or total this week/)).toBeInTheDocument()
    const strip = screen.getByRole('group', { name: 'Betting card summary' })
    expect(strip).toHaveTextContent('4 of 4')
    expect(strip).toHaveTextContent('No bets logged')
    expect(strip).toHaveTextContent('Week 11')
  })

  it('shows what a bet needs: the price, the exchange cents, the best book now', async () => {
    renderRoute('/betting/week')
    const buf = (await screen.findByRole('heading', { level: 3, name: 'BUF to win' })).closest('div')!.parentElement!
    expect(within(buf).getByText('Only at −944 or better')).toBeInTheDocument()
    expect(within(buf).getByText(/On an exchange: 89¢ or less/)).toBeInTheDocument()
    expect(within(buf).getByText(/Best licensed book now: −1,?400 \(BetMGM\)/)).toBeInTheDocument()
    expect(within(buf).getByText(/worse than fair, as book prices nearly always are/)).toBeInTheDocument()
    expect(within(buf).getByText(/Student 92%, market 90%/)).toBeInTheDocument()
    expect(within(buf).getByText(/Stake: 1% of your bankroll/)).toBeInTheDocument()
  })

  it('works a stake out of a typed bankroll and keeps it', async () => {
    const user = userEvent.setup()
    renderRoute('/betting/week')
    await user.type(await screen.findByLabelText('Your bankroll'), '2000')
    const buf = screen.getByRole('heading', { level: 3, name: 'BUF to win' }).closest('div')!.parentElement!
    expect(within(buf).getByText(/Stake: \$20 to win \$1\.43/)).toBeInTheDocument() // 20 × (1 + 100/1400 − 1)
    expect(within(screen.getByRole('group', { name: 'Betting card summary' })).getByText('$20')).toBeInTheDocument()
    expect(localStorage.getItem('nfl-bankroll-v1')).toBe('2000')
  })

  it('logs a bet from a card: prefilled, added, open until the game is played', async () => {
    const user = userEvent.setup()
    renderRoute('/betting/week')
    await user.type(await screen.findByLabelText('Your bankroll'), '1000')
    const buf = screen.getByRole('heading', { level: 3, name: 'BUF to win' }).closest('div')!.parentElement!
    await user.click(within(buf).getByRole('button', { name: 'Log this bet' }))
    const form = await screen.findByRole('form', { name: 'Log a bet' })
    expect(within(form).getByLabelText('Price')).toHaveValue('-944')
    expect(within(form).getByLabelText('Stake ($)')).toHaveValue('10')
    expect(within(form).getByLabelText('Game')).toHaveDisplayValue(/MIA @ BUF/)
    await user.click(within(form).getByRole('button', { name: 'Add to my log' }))
    const table = (await screen.findByRole('columnheader', { name: 'Game' })).closest('table')!
    expect(within(table).getByText('BUF to win')).toBeInTheDocument()
    expect(within(table).getByText('Open')).toBeInTheDocument()
    expect(getBets()).toHaveLength(1)
    expect(getBets()[0]).toMatchObject({ game_id: '2026_11_MIA_BUF', market: 'ml', side: 'home', price: -944, stake: 10 })
  })

  it('refuses a price inside ±100 and a missing stake', async () => {
    const user = userEvent.setup()
    renderRoute('/betting/week?tab=log')
    const form = await screen.findByRole('form', { name: 'Log a bet' })
    await user.type(within(form).getByLabelText('Price'), '50')
    await user.type(within(form).getByLabelText('Stake ($)'), '10')
    await user.click(within(form).getByRole('button', { name: 'Add to my log' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/American price/)
    expect(getBets()).toHaveLength(0)
  })

  it('takes a price in cents and stores it as American', async () => {
    const user = userEvent.setup()
    renderRoute('/betting/week?tab=log')
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
    renderRoute('/betting/week?tab=log')
    const table = (await screen.findByRole('columnheader', { name: 'Game' })).closest('table')!
    const row = within(table).getByText('WAS to win').closest('tr')!
    expect(within(row).getByText('Won')).toBeInTheDocument()
    expect(within(row).getByText('+$15.00')).toBeInTheDocument()
    expect(within(row).getByText('+7.6 pts')).toBeInTheDocument()
    expect(within(row).getByText('+150')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Betting card summary' })).toHaveTextContent('+$15.00')
    expect(screen.getByText("The card's paper record at the locks")).toBeInTheDocument()
  })

  it('deletes a bet', async () => {
    const user = userEvent.setup()
    localStorage.setItem(BETS_KEY, JSON.stringify([seeded()]))
    renderRoute('/betting/week?tab=log')
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
    renderRoute('/betting/week?tab=log')
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
    renderRoute('/betting/week?tab=log')
    const input = (await screen.findByText('Import JSON')).querySelector('input')!
    const file = new File([JSON.stringify([seeded({ id: 'imp' }), { id: 'bad' }])], 'bets.json', { type: 'application/json' })
    await user.upload(input, file)
    expect(await screen.findByText(/Imported 1 new bet; skipped 1 that couldn’t be read\./)).toBeInTheDocument()
    expect(getBets().map((e) => e.id)).toEqual(['imp'])
  })

  it('record tab: the paper record and the rule in history', async () => {
    renderRoute('/betting/week?tab=record')
    expect(await screen.findByText('What following the card would have returned.')).toBeInTheDocument()
    expect(screen.getByText('At the consensus price at each lock, 1 unit a bet.')).toBeInTheDocument()
    expect(screen.getAllByText('Worth a look').length).toBeGreaterThan(0)
    expect(screen.getByText('+1.95')).toBeInTheDocument()
  })
})
