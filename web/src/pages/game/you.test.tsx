import fs from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Game, Meta } from '../../data/contract'
import { APPROACHES } from '../../lib/models'
import { LinesContext, NO_LINES, type Lines } from '../../you/current'
import { Differ } from './Differ'
import { ApproachesVsMarket, Why } from './Sections'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const load = (p: string) => JSON.parse(fs.readFileSync(path.join(FIX, p), 'utf8'))
const meta = Meta.parse(load('meta.json'))
const base = Game.parse(load('game/2026_08_CAR_GB.json'))
const g: Game = {
  ...base,
  models: { ...base.models, you: { ...base.models.student, p_home: 0.2, spread_home: 6, status: 'preview' as const, divergence: -0.3 } },
  contributions: { ...base.contributions, you: base.contributions.student },
}
const lines = (headline: string): Lines => ({ ...NO_LINES, headline, approaches: APPROACHES })
const wrap = (headline: string, ui: React.ReactNode) => render(<LinesContext.Provider value={lines(headline)}>{ui}</LinesContext.Provider>)

describe('the game page with your line', () => {
  it('Why starts on your line when it is the headline, and notes the missing detail', () => {
    wrap('you', <Why g={g} meta={meta} />)
    expect(screen.getByRole('radio', { name: 'You' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText(/has no per-feature detail/)).toBeInTheDocument()
  })
  it('Why starts on the first option otherwise, with no note', () => {
    wrap('student', <Why g={g} meta={meta} />)
    expect(screen.getByRole('radio', { name: 'You' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.queryByText(/has no per-feature detail/)).toBeNull()
  })
  it('the approaches table tags your row unofficial', () => {
    wrap('student', <ApproachesVsMarket g={g} meta={meta} />)
    expect(screen.getAllByText('unofficial')).toHaveLength(1)
  })
  it('the differ names your line without "The You"', () => {
    const market = g.market?.p_home ?? g.models.market_baseline?.p_home ?? 0.5
    const far = { ...g, strong_calls: [], models: { ...g.models, you: { ...g.models.you, p_home: Math.max(0.01, market - 0.3) } } }
    wrap('you', <Differ g={far} meta={meta} />)
    expect(screen.queryByText(/The You/)).toBeNull()
    expect(screen.getByText(/^Your line has /)).toBeInTheDocument()
  })
})
