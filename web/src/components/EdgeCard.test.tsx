import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { Game } from '../data/contract'
import { ordinal } from '../lib/rank'
import { EdgeCard } from './EdgeCard'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json')
const g = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const sides = g.edge_cards!
const colorOf = (t: string) => (t === g.home ? 'var(--team-home)' : 'var(--team-away)')

describe('EdgeCard', () => {
  it('the fixture has an underdog and a favorite, each with levers', () => {
    expect(sides.map((s) => s.role)).toEqual(['underdog', 'favorite'])
    for (const s of sides) expect(s.levers.length).toBeGreaterThan(0)
  })

  for (const i of [0, 1]) {
    it(`full card ${i}: one card per lever with both ranks and the history, chips, no checks before the game`, () => {
      const s = sides[i]
      render(<EdgeCard side={s} colorOf={colorOf} />)
      expect(screen.getByRole('heading', { name: new RegExp(`Where ${s.team} has the edge`) })).toBeInTheDocument()
      for (const lv of s.levers) {
        const card = screen.getByTestId(`lever-${lv.id}`)
        expect(within(card).getByText(lv.label)).toBeInTheDocument()
        expect(within(card).getByText(`${s.team}'s ${lv.dog_noun}`)).toBeInTheDocument()
        expect(within(card).getByText(`${s.opponent}'s ${lv.fav_noun}`)).toBeInTheDocument()
        expect(card.textContent).toContain(ordinal(lv.dog_rank))
        expect(card.textContent).toContain(ordinal(lv.fav_rank))
        expect(card.textContent).toContain(`${lv.win_rate_pct}%`)
        expect(card.textContent).toContain(`${lv.base_rate_pct}%`)
        expect(card.textContent).toContain(s.role === 'underdog' ? "Underdogs' win rate" : "Favorites' win rate")
        expect(within(card).getByTestId('lever-plausibility').textContent?.includes('luck')).toBe(lv.plausibility.startsWith('coin flip'))
      }
      for (const c of s.chips) expect(screen.getByTestId(`chip-${c.id}`)).toHaveAttribute('data-kind', c.kind)
      expect(document.querySelector('[data-met]')).toBeNull()
    })
  }

  it('after the game marks each lever the team won', () => {
    const s = { ...sides[1], met: [sides[1].levers[0].id] }
    render(<EdgeCard side={s} colorOf={colorOf} />)
    for (const lv of s.levers) {
      const mark = screen.getByTestId(`lever-${lv.id}`).querySelector('[data-met]')
      expect(mark?.getAttribute('data-met')).toBe(lv.id === s.levers[0].id ? 'yes' : 'no')
    }
  })

  it('compact: one row per lever with ranks and win rates, no chips', () => {
    const s = sides[0]
    render(<EdgeCard side={s} colorOf={colorOf} compact />)
    for (const lv of s.levers) {
      const row = screen.getByTestId(`lever-${lv.id}`)
      expect(row.textContent).toContain(`${ordinal(lv.dog_rank)} vs ${ordinal(lv.fav_rank)}`)
      expect(row.textContent).toContain(`${lv.base_rate_pct}% → ${lv.win_rate_pct}%`)
    }
    expect(screen.queryByTestId(/^chip-/)).toBeNull()
  })

  it('without levers says so', () => {
    render(<EdgeCard side={{ ...sides[0], levers: [] }} colorOf={colorOf} compact />)
    expect(screen.getByText(`No clear mismatch for ${sides[0].team}.`)).toBeInTheDocument()
  })

  it('prints no percentage that is not in the JSON', () => {
    const { container } = render(
      <>
        {sides.map((s) => (
          <EdgeCard key={s.team} side={s} colorOf={colorOf} />
        ))}
      </>,
    )
    const allowed = new Set(sides.flatMap((s) => [s.base_rate_pct, ...s.levers.flatMap((l) => [l.win_rate_pct, l.base_rate_pct])]).map((n) => `${n}%`))
    for (const m of (container.textContent ?? '').matchAll(/\d+%/g)) expect(allowed.has(m[0])).toBe(true)
    expect(container.textContent ?? '').not.toMatch(/chance|probab/i)
  })
})
