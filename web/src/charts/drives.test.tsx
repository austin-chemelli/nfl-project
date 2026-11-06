import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Drive } from '../data/contract'
import { DriveField, driveGlyph } from './DriveField'
import { isScore, PossessionStrip, type DriveTip } from './PossessionStrip'
import { timeScale } from './wpScale'

vi.mock('./useWidth', () => ({ useWidth: () => [() => undefined, 600] }))

const d = (n: number, team: string, t0: number, t1: number, result: string | null, start: number | null = 25, end: number | null = 40, qtr = 1): Drive =>
  ({ n, team, qtr, t0, t1, start_yl: start, end_yl: end, plays: 5, result })
const drives = [d(1, 'ARI', 0, 200, 'Punt'), d(2, 'DAL', 210, 500, 'Touchdown', 30, 99), d(3, 'ARI', 510, 900, 'Field goal', 20, 70), d(4, 'DAL', 905, 1000, 'Turnover', 12, 12, 2)]
const describeDrive = (x: Drive): DriveTip => ({ title: `Q${x.qtr} · ${x.team}`, result: x.result ?? '?', span: '5 plays, 3:20', detail: 'From own 25' })

describe('PossessionStrip', () => {
  const strip = () => render(<PossessionStrip drives={drives} endT={3600} home="DAL" describe={describeDrive} />)

  it('draws one segment per drive, in time order, each running to the next drive', () => {
    strip()
    const xs = screen.getAllByTestId('drive-segment').map((r) => Number(r.getAttribute('x')))
    expect(xs).toHaveLength(4)
    expect(xs).toEqual([...xs].sort((a, b) => a - b))
  })

  it('sits on the win-probability chart\'s time axis', () => {
    strip()
    const x = timeScale(600, 3600)
    const seg = screen.getAllByTestId('drive-segment')
    expect(Number(seg[1].getAttribute('x'))).toBeCloseTo(x(210))
    expect(Number(seg[3].getAttribute('x'))).toBeCloseTo(x(905))
    expect(Number(seg[3].getAttribute('x')) + Number(seg[3].getAttribute('width')) + 1).toBeCloseTo(x(3600))
  })

  it('colors a segment by the team with the ball, and ticks each score at its end', () => {
    strip()
    const seg = screen.getAllByTestId('drive-segment')
    expect(seg[0]).toHaveAttribute('fill', 'var(--team-away)')
    expect(seg[1]).toHaveAttribute('fill', 'var(--team-home)')
    const ticks = screen.getAllByTestId('drive-score')
    expect(ticks).toHaveLength(2)
    expect(Number(ticks[0].getAttribute('x1'))).toBeCloseTo(timeScale(600, 3600)(500))
  })

  it('counts a defensive score, and shows a drive on tap without a tab stop', () => {
    expect(isScore(d(1, 'A', 0, 1, 'Opp touchdown'))).toBe(true)
    expect(isScore(d(1, 'A', 0, 1, 'Safety'))).toBe(true)
    expect(isScore(d(1, 'A', 0, 1, 'Punt'))).toBe(false)
    const { container } = strip()
    expect(container.querySelector('[tabindex="0"]')).toBeNull()
    fireEvent.focus(container.querySelectorAll('[tabindex="-1"]')[1])
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('Touchdown')
  })
})

describe('DriveField', () => {
  const field = (ds = drives) => render(<DriveField drives={ds} home="DAL" away="ARI" describe={describeDrive} />)

  it('maps each result to its glyph', () => {
    expect(['Touchdown', 'Field goal', 'Missed field goal', 'Punt', 'Turnover', 'Turnover on downs', 'Opp touchdown', 'Safety', 'End of half', null].map(driveGlyph))
      .toEqual(['score', 'kick', 'miss', 'punt', 'lost', 'lost', 'lost', 'lost', null, null])
  })

  it('draws one row per drive with its glyph', () => {
    const { container } = field()
    expect(screen.getAllByTestId('drive-row')).toHaveLength(4)
    const rows = screen.getAllByTestId('drive-row')
    expect(rows[1].querySelector('[data-glyph="score"]')).not.toBeNull()
    expect(rows[3].querySelector('[data-glyph="lost"]')).not.toBeNull()
    expect(container.querySelectorAll('svg').length).toBeGreaterThan(1) // the legend
  })

  it('drives the away team toward the home end zone and the home team back, and takes a touchdown to the goal line', () => {
    field()
    const [away, home] = screen.getAllByTestId('drive-bar')
    expect(away.style.transformOrigin).toBe('left')
    expect(home.style.transformOrigin).toBe('right')
    const left = 72
    const right = 596
    const yard = (v: number) => left + ((v + 10) / 120) * (right - left)
    expect(Number(away.getAttribute('x'))).toBeCloseTo(yard(25))
    expect(Number(home.getAttribute('x'))).toBeCloseTo(yard(0)) // home's drive from its 30 ends at the away goal line
  })

  it('handles a null yard line and a 50', () => {
    field([d(1, 'ARI', 0, 200, 'Punt', null, null), d(2, 'DAL', 210, 400, 'End of half', 50, 50)])
    const rows = screen.getAllByTestId('drive-row')
    expect(rows[0].querySelector('[data-testid="drive-bar"]')).toBeNull()
    expect(rows[1].querySelector('[data-testid="drive-bar"]')).not.toBeNull()
  })

  it('shows a tip on focus and marks a new quarter', () => {
    field()
    fireEvent.focus(screen.getAllByTestId('drive-row')[2])
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('Field goal')
    expect(screen.getByText('Q1')).toBeInTheDocument()
    expect(screen.getByText('Q2')).toBeInTheDocument()
  })
})
