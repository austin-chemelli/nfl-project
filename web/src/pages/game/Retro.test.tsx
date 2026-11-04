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
    expect(screen.getByText(/The Traditionalist came closest/)).toBeInTheDocument()
    const best = container.querySelectorAll('tr[data-best]')
    expect(best).toHaveLength(1)
    expect(within(best[0] as HTMLElement).getByText('The Traditionalist')).toBeInTheDocument()
    expect(within(best[0] as HTMLElement).getByText('Best')).toBeInTheDocument()
    const market = screen.getByText('Market').closest('tr') as HTMLElement
    expect(within(market).getByText('reference')).toBeInTheDocument()
  })

  it('shows played-like, a luck sentence, net luck and the most valuable group', () => {
    render(<Retro r={r} />)
    expect(screen.getByRole('img', { name: /Played like: GB 61%, CAR 39%/ })).toBeInTheDocument()
    expect(screen.getByText('✓ won')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /GB: net swing −9\.6 pts/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /CAR: net swing \+5\.3 pts/ })).toBeInTheDocument()
    expect(screen.getAllByText(/lost 3 of its 3 fumbles; about 1\.6/).length).toBeGreaterThan(0)
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
    expect(screen.getAllByRole('heading', { name: /net swing/ })).toHaveLength(2)
  })
})
