import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import type { GameRow, Meta } from '../../data/contract'
import { LinesContext, NO_LINES, type Lines } from '../../you/current'
import { GameCard } from './GameCard'

const pick = (p: number) => ({ p_home: p, spread_home: -3, status: 'preview' as const, lock_ts: null, divergence: null })
const g = {
  game_id: 'g', season: 2026, week: 8, kickoff_utc: '2026-10-30T00:15:00Z', away: 'CAR', home: 'GB', stadium: null, roof: null,
  neutral_site: false, away_qb: null, home_qb: null, result: null, market: null, card: null, line_move: null, composites: null,
  models: { student: pick(0.7), you: pick(0.3) },
} as unknown as GameRow

const show = (lines: Lines) =>
  render(
    <MemoryRouter>
      <LinesContext.Provider value={lines}>
        <GameCard g={g} meta={{ current_week: 8 } as Meta} showStatus={false} />
      </LinesContext.Provider>
    </MemoryRouter>,
  )

describe('GameCard pick line', () => {
  it('leads with the Student by default', () => {
    show(NO_LINES)
    expect(screen.getByText(/Student's pick: GB 70%/)).toBeInTheDocument()
  })
  it('says "Your line\'s pick" and tags it unofficial when the reader line leads', () => {
    show({ ...NO_LINES, headline: 'you' })
    expect(screen.getByText(/Your line's pick: CAR 70%/)).toBeInTheDocument()
    expect(screen.getAllByText('unofficial').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Student's pick/)).toBeNull()
  })
})
