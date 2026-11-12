import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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

  it('words each habit from the JSON, the defense first, with the evidence label', () => {
    const side = g.matchups!.sides[0]
    render(<HabitList rows={side.rows} offense={side.offense} defense={side.defense} colorOf={colorOf} pass={{ team: side.offense, rate: 0.6, league: 0.58 }} />)
    expect(screen.getByTestId('habit-pass')).toHaveTextContent(`${side.offense} passes on 60% of plays`)
    const items = screen.getAllByRole('listitem').slice(1)
    const shown = side.rows.filter((r) => r.has_edge && r.chooser !== 'neither' && r.opp_rate != null)
    expect(items).toHaveLength(shown.length)
    const choosers = items.map((li) => shown.find((r) => li.getAttribute('data-testid') === `habit-${r.split}`)!.chooser)
    expect(choosers.indexOf('offense') === -1 || choosers.lastIndexOf('defense') < choosers.indexOf('offense')).toBe(true)
    for (const r of shown) {
      const li = screen.getByTestId(`habit-${r.split}`)
      expect(li.textContent).toContain(`${Math.round(100 * r.opp_rate!)}%`)
      expect(li.querySelector('[data-reliability]')?.textContent).toBe(EVIDENCE[r.reliability])
      const v = within(li).getByTestId('habit-verdict').textContent ?? ''
      if (r.edge_pts_pg != null && Math.abs(r.edge_pts_pg) >= 0.05) expect(v).toContain(Math.abs(r.edge_pts_pg).toFixed(2))
      else expect(v).toBe('About even')
    }
  })
})
