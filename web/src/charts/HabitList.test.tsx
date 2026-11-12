import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Game } from '../data/contract'
import { HabitList } from './HabitList'
import { quartile } from '../lib/rank'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json')
const g = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const colorOf = (t: string) => (t === g.home ? 'var(--team-home)' : 'var(--team-away)')
const EVIDENCE = { noise: 'thin evidence', some: 'some evidence', stable: 'solid evidence' }

describe('HabitList', () => {
  it('quartile', () => {
    const b = { opp_rate_q1: 0.2, opp_rate_med: 0.3, opp_rate_q3: 0.4 }
    expect([0.1, 0.25, 0.35, 0.45].map((v) => quartile({ ...b, opp_rate: v }))).toEqual([1, 2, 3, 4])
    expect(quartile({ ...b, opp_rate: null })).toBeNull()
  })

  it('one light line per habit, the defense first; the detail waits for the hover card', async () => {
    const side = g.matchups!.sides[0]
    render(<HabitList rows={side.rows} offense={side.offense} defense={side.defense} colorOf={colorOf} pass={{ team: side.offense, rate: 0.6, league: 0.58 }} />)
    expect(screen.getByTestId('habit-pass')).toHaveTextContent(`${side.offense} passes 60%`)
    const shown = side.rows.filter((r) => r.has_edge && r.chooser !== 'neither' && r.opp_rate != null)
    const items = screen.getAllByRole('listitem').slice(1)
    expect(items).toHaveLength(shown.length)
    const choosers = items.map((li) => shown.find((r) => li.getAttribute('data-testid') === `habit-${r.split}`)!.chooser)
    expect(choosers.indexOf('offense') === -1 || choosers.lastIndexOf('defense') < choosers.indexOf('offense')).toBe(true)
    for (const r of shown) {
      const li = screen.getByTestId(`habit-${r.split}`)
      expect(li.textContent).not.toMatch(/EPA|evidence|\d/) // no numbers or jargon on the line itself
      const pill = within(li).getByTestId('habit-verdict')
      const fav = r.favours === 'offense' ? side.offense : side.defense
      if (r.edge_pts_pg != null && Math.abs(r.edge_pts_pg) >= 0.05) expect(pill).toHaveAttribute('data-team', fav)
      else expect(pill.textContent).toBe('even')
    }
    // the hover card has the numbers and the evidence label
    const r = shown[0]
    await userEvent.hover(screen.getByTestId(`habit-${r.split}`))
    fireEvent.pointerMove(screen.getByTestId(`habit-${r.split}`), { clientX: 10, clientY: 10 })
    expect(await screen.findByText(EVIDENCE[r.reliability])).toBeInTheDocument()
    expect(screen.getByText(`${Math.round(100 * r.opp_rate!)}%`)).toBeInTheDocument()
  })
})
