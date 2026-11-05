import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SeasonGrid } from './SeasonGrid'

const row = (season: number, units: number) => ({ model_id: 'student', season, units, bets: 10, no_edge_units: -1 })

describe('SeasonGrid', () => {
  it('counts finished seasons only in "up of played"', () => {
    const rows = [row(2024, 3), row(2025, -2), row(2026, 5)]
    render(<SeasonGrid rows={rows as never} ids={['student']} current={2026} />)
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
  })
})
