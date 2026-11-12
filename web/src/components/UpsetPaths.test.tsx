import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { Game } from '../data/contract'
import { ordinal } from '../lib/rank'
import { UpsetPaths } from './UpsetPaths'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json')
const g = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const paths = g.paths!

const tier1 = new Set(paths.levers.filter((l) => l.tier === 1).map((l) => l.id))
const outcome = {
  game_id: paths.game_id ?? 'x',
  dog: paths.dog,
  favorite: paths.favorite,
  size: paths.size,
  bucket: paths.bucket,
  dog_won: true,
  tied: false,
  margin: 3,
  // outcomes list tier-1 conditions only (nfl.paths)
  conditions: paths.conditions.filter((c) => !['run_game', 'deep_passes', 'red_zone'].includes(c.id)).map((c, i) => ({ id: c.id, label: c.label, met: i % 2 === 0 })),
  met: [],
  sentence: 'CAR converted more third downs; it won.',
}

describe('UpsetPaths', () => {
  it('fixture has levers and chips to draw', () => {
    expect(paths.levers.length).toBeGreaterThan(0)
    expect(paths.chips.length).toBeGreaterThan(0)
  })

  it('draws one card per lever with both ranks and the history from the JSON', () => {
    render(<UpsetPaths paths={paths} />)
    expect(screen.getByRole('heading', { name: new RegExp(`Where ${paths.dog} has the edge`) })).toBeInTheDocument()
    for (const lv of paths.levers) {
      const card = screen.getByTestId(`lever-${lv.id}`)
      expect(within(card).getByText(lv.label)).toBeInTheDocument()
      expect(within(card).getByText(`${paths.dog}'s ${lv.dog_noun}`)).toBeInTheDocument()
      expect(within(card).getByText(`${paths.favorite}'s ${lv.fav_noun}`)).toBeInTheDocument()
      expect(card.textContent).toContain(ordinal(lv.dog_rank))
      expect(card.textContent).toContain(ordinal(lv.fav_rank))
      expect(card.textContent).toContain(`${lv.win_rate_pct}%`)
      expect(card.textContent).toContain(`${lv.base_rate_pct}%`)
      const label = within(card).getByTestId('lever-plausibility').textContent ?? ''
      expect(label.includes('luck')).toBe(lv.plausibility.startsWith('coin flip'))
    }
    for (const c of paths.chips) expect(screen.getByTestId(`chip-${c.id}`)).toHaveAttribute('data-kind', c.kind)
    expect(screen.queryByTestId('paths-outcome')).toBeNull()
    expect(screen.queryByRole('img', { name: 'met' })).toBeNull()
  })

  it('without levers says so in the record sentence', () => {
    render(<UpsetPaths paths={{ ...paths, levers: [], sentence: 'No clear mismatch for CAR.' }} />)
    expect(screen.getByText(/No clear mismatch for CAR\./)).toBeInTheDocument()
    expect(screen.queryByTestId(/^lever-/)).toBeNull()
  })

  it('hides entirely without paths', () => {
    const { container } = render(<UpsetPaths paths={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('checks the levers the dog met after the game; tier-2 levers have no mark', () => {
    render(<UpsetPaths paths={paths} outcome={outcome} />)
    const byId = new Map(outcome.conditions.map((c) => [c.id, c.met]))
    for (const lv of paths.levers) {
      const card = screen.getByTestId(`lever-${lv.id}`)
      const mark = card.querySelector('[data-met]')
      if (tier1.has(lv.id)) expect(mark?.getAttribute('data-met')).toBe(byId.get(lv.id) ? 'yes' : 'no')
      else expect(mark).toBeNull()
    }
    expect(screen.getByTestId('paths-outcome')).toHaveTextContent(outcome.sentence)
  })

  it('prints no percentage that is not in the JSON', () => {
    const { container } = render(<UpsetPaths paths={paths} outcome={outcome} />)
    const allowed = new Set([paths.base_rate_pct, ...paths.levers.flatMap((l) => [l.win_rate_pct, l.base_rate_pct])].map((n) => `${n}%`))
    for (const m of (container.textContent ?? '').matchAll(/\d+%/g)) expect(allowed.has(m[0])).toBe(true)
    expect(container.textContent ?? '').not.toMatch(/chance|probab/i)
  })
})
