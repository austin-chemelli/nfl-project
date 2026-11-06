import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RetroGame } from '../../data/contract'
import { Retro } from './Retro'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site/retro/2026_08_CAR_GB.json')
const r = RetroGame.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))

describe('Retro', () => {
  it('renders headlines and the forecast table with the best model highlighted', () => {
    const { container } = render(<Retro r={r} />)
    expect(screen.getAllByText(/Green Bay lost 3 of its 3 fumbles/, { selector: 'li' }).length).toBeGreaterThan(0)
    expect(screen.queryByText(/came closest/)).toBeNull()
    const best = container.querySelectorAll('tr[data-best]')
    expect(best).toHaveLength(1)
    expect(within(best[0] as HTMLElement).getByText('The Traditionalist')).toBeInTheDocument()
    expect(within(best[0] as HTMLElement).getByText('Best')).toBeInTheDocument()
    const market = screen.getByText('Market').closest('tr') as HTMLElement
    expect(within(market).getByText('reference')).toBeInTheDocument()
  })

  it('shows played-like with what goes into it, and leaves it out on a record from before schema 3', () => {
    const { unmount } = render(<Retro r={r} />)
    expect(screen.getByRole('img', { name: /Played like: GB 61%, CAR 39%/ })).toBeInTheDocument()
    expect(screen.getByText('✓ won')).toBeInTheDocument()
    expect(screen.getByText('decides it')).toBeInTheDocument()
    expect(screen.getByText('context')).toBeInTheDocument()
    expect(screen.getByText(/Before any plays, the home side wins 59% of the time\. GB's edge of 0\.009 EPA a play moves GB to 61%\./)).toBeInTheDocument()
    unmount()
    const old = structuredClone(r)
    Object.assign(old.played_like, { home_epa: null, away_epa: null, home_success: null, away_success: null, p_base: null })
    render(<Retro r={old} />)
    expect(screen.queryByText('decides it')).toBeNull()
  })

  it('splits the swing plays into variance and pure luck, and hides Global', () => {
    render(<Retro r={r} />)
    expect(screen.getByRole('heading', { name: /^Swing plays/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Variance' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Pure luck' })).toBeInTheDocument()
    expect(screen.getByText('CAR +14.9')).toBeInTheDocument() // GB net −9.6, CAR +5.3
    expect(screen.getAllByText(/lost 3 of its 3 fumbles; about 1\.6/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Global fit/)).toBeNull()
  })

  it('shows who won each phase, and nothing on a record without them', () => {
    const { container, unmount } = render(<Retro r={r} />)
    expect(screen.getByRole('heading', { name: /^Phase by phase/ })).toBeInTheDocument()
    expect(screen.getByText('CAR won 4 of 8 phases')).toBeInTheDocument() // GB 3, one even
    expect(container.querySelectorAll('[data-won]')).toHaveLength(7)
    expect(screen.getByText('2 of 4')).toBeInTheDocument()
    unmount()
    render(<Retro r={{ ...r, phases: [] }} />)
    expect(screen.queryByRole('heading', { name: /^Phase by phase/ })).toBeNull()
  })

  it('names the most valuable group', () => {
    render(<Retro r={r} />)
    // defaults to the best model (Traditionalist); its most valuable group is labeled
    expect(screen.getByText(/Most valuable for The Traditionalist/)).toBeInTheDocument()
    expect(screen.getByText(/read their order, not their size/)).toBeInTheDocument()
  })

  it('switches approach in the groups section', async () => {
    render(<Retro r={r} />)
    await userEvent.click(within(screen.getByRole('radiogroup', { name: 'Approach' })).getByRole('radio', { name: 'Analyst' }))
    expect(screen.getByText(/Most valuable for The Analyst/)).toBeInTheDocument()
    expect(screen.getByText('Offensive scheme', { selector: 'b' })).toBeInTheDocument()
  })

  it('renders a week-1 retro with no season-to-date or league values', () => {
    const w1 = structuredClone(r)
    for (const t of [w1.teams.home, w1.teams.away]) for (const e of t.efficiency) Object.assign(e, { season: null, league: null, season_games: 0 })
    render(<Retro r={w1} />)
    expect(screen.getByRole('heading', { name: 'Variance' })).toBeInTheDocument()
  })

  it('puts "How it unfolded" right after the headlines, with the turning points matching the marks', () => {
    const { container } = render(<Retro r={r} />)
    const heads = [...container.querySelectorAll('h2')].map((h) => h.textContent)
    const order = ['What happened', 'How it unfolded', 'Played like']
    expect(heads.slice(0, 3).map((t, i) => t?.startsWith(order[i]))).toEqual([true, true, true])
    expect(screen.getByText(/CAR won 23–20 after its win chance fell to 16% in Q2\./)).toBeInTheDocument()
    const items = screen.getAllByRole('listitem').filter((li) => li.closest('ol'))
    const marks = screen.getAllByTestId('wp-mark')
    expect(items).toHaveLength(marks.length)
    expect(items[1]).toHaveTextContent('Q4 3:02 · GB: CAR win chance 36% → 79% (+43 pts). (Shotgun) J.Love')
    expect(items[1]).toHaveTextContent('Counted in: Fumble recoveries.')
    expect(screen.getByText('Turning points')).toBeInTheDocument()
    expect(screen.getByText(/not one of this site's approaches/)).toBeInTheDocument()
  })

  it('renders no win-probability section when wp_series is null or missing', () => {
    const { unmount } = render(<Retro r={{ ...r, wp_series: null }} />)
    expect(screen.queryByRole('heading', { name: /How it unfolded/ })).toBeNull()
    expect(screen.queryByText('Turning points')).toBeNull()
    unmount()
    const { wp_series: _omit, ...rest } = r
    render(<Retro r={rest as typeof r} />)
    expect(screen.queryByRole('heading', { name: /How it unfolded/ })).toBeNull()
  })
})
