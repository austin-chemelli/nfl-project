import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import { PlayerClaimGrade, type Tracker } from '../../data/contract'
import { PlayerClaims } from './PlayerClaims'

afterEach(cleanup)
const row = PlayerClaimGrade.parse({
  game_id: '2026_11_KC_BUF', season: 2026, week: 11, team: 'KC', opponent: 'BUF', player: 'Pat Mahomes', pos: 'QB', grp: 'QB',
  status_before: 'Questionable', p_play: 0.7, value_pts: 4, expected: 2.5, moved: 1.5, hours: 20, out_seen: '2026-11-15T12:00:00Z', margin_vs_line: -3,
})
const ui = (pc: unknown) => render(<MemoryRouter><PlayerClaims t={{ player_claims: pc } as unknown as Tracker} /></MemoryRouter>)

describe('PlayerClaims', () => {
  it('says nothing has been graded with 0 graded', () => {
    ui({ first_pass: '2026-11-10', claims: 3, graded: 0, mean_expected: null, mean_moved: null, rows: [] })
    expect(screen.getByText(/No claim has been graded yet/)).toBeInTheDocument()
    expect(screen.getByText(/2026-11-10/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('shows the means and the graded rows', () => {
    ui({ first_pass: '2026-11-10', claims: 5, graded: 1, mean_expected: 2.5, mean_moved: 1.5, rows: [row] })
    expect(screen.getByText(/claims made/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Pat Mahomes' })).toBeInTheDocument()
    expect(screen.getByText('Questionable')).toBeInTheDocument()
    expect(screen.getByText('-3.0')).toBeInTheDocument()
  })

  it('is hidden when null', () => {
    expect(ui(null).container).toBeEmptyDOMElement()
  })
})
