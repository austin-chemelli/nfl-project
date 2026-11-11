import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Game } from '../data/contract'
import { UpsetPaths } from './UpsetPaths'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json')
const g = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const paths = g.paths!

const outcome = {
  game_id: paths.game_id ?? 'x',
  dog: paths.dog,
  favorite: paths.favorite,
  size: paths.size,
  bucket: paths.bucket,
  dog_won: true,
  tied: false,
  margin: 3,
  conditions: paths.conditions.map((c, i) => ({ id: c.id, label: c.label, met: i % 2 === 0 })),
  met: [],
  sentence: 'CAR won the turnover battle; it won.',
}

describe('UpsetPaths', () => {
  it('renders every condition with history, this dog and this favourite, and the sentence verbatim', () => {
    render(<UpsetPaths paths={paths} />)
    expect(screen.getByRole('heading', { name: new RegExp(`How ${paths.dog} wins`) })).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`Underdogs of this size won ${paths.base_rate_pct}%`))).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(paths.conditions.length)
    for (const c of paths.conditions) {
      expect(screen.getByText(c.label)).toBeInTheDocument()
      expect(screen.getByText(`(n ${c.n})`)).toBeInTheDocument()
    }
    expect(screen.getByText(paths.sentence)).toBeInTheDocument()
    expect(document.querySelectorAll('[data-top]')).toHaveLength(paths.top.length)
    expect(screen.queryByTestId('paths-outcome')).toBeNull()
    expect(screen.queryByRole('img', { name: 'met' })).toBeNull()
  })

  it('hides entirely without paths', () => {
    const { container } = render(<UpsetPaths paths={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a check or dash per condition and the outcome sentence for a finished game', () => {
    render(<UpsetPaths paths={paths} outcome={outcome} />)
    const yes = outcome.conditions.filter((c) => c.met).length
    expect(screen.getAllByRole('img', { name: 'met' })).toHaveLength(yes)
    expect(screen.getAllByRole('img', { name: 'not met' })).toHaveLength(outcome.conditions.length - yes)
    expect(screen.getByTestId('paths-outcome')).toHaveTextContent(outcome.sentence)
  })

  it('prints no percentage that is not in the JSON', () => {
    const { container } = render(<UpsetPaths paths={paths} outcome={outcome} />)
    const allowed = new Set([paths.base_rate_pct, ...paths.conditions.map((c) => c.win_rate_pct)].map((n) => `${n}%`))
    for (const m of (container.textContent ?? '').matchAll(/\d+%/g)) {
      const inSentence = paths.sentence.includes(m[0]) || outcome.sentence.includes(m[0])
      expect(allowed.has(m[0]) || inSentence).toBe(true)
    }
    expect(container.textContent ?? '').not.toMatch(/chance|probab/i)
  })
})
