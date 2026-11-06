import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RangeRow, type RangeRowData } from './RangeRow'

const f = (v: number) => v.toFixed(2)
const row = (o: Partial<RangeRowData>): RangeRowData => ({ key: 'epa', label: 'EPA/play', game: 0.2, season: 0.15, league: 0.02, lo: -0.1, hi: 0.12, verdict: 'better', ...o })

describe('RangeRow', () => {
  it('draws the band and prints the value and a positive delta', () => {
    const { container } = render(<RangeRow rows={[row({})]} format={f} />)
    expect(screen.getByTestId('band')).toBeInTheDocument()
    expect(container.textContent).toContain('0.20')
    expect(container.textContent).toContain('+0.05 vs season')
    expect(screen.getByText('Typical range')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('EPA/play 0.20, +0.05 vs season'))
  })

  it('prints a negative delta with a minus sign', () => {
    const { container } = render(<RangeRow rows={[row({ game: 0.1, season: 0.15, verdict: 'worse' })]} format={f} />)
    expect(container.textContent).toContain('−0.05 vs season')
  })

  it('without a band falls back and says so; an outlier game is still drawn', () => {
    const { container } = render(<RangeRow rows={[row({ lo: null, hi: null, game: 5 })]} format={f} />)
    expect(screen.queryByTestId('band')).not.toBeInTheDocument()
    expect(container.textContent).toContain('no league range')
    expect(container.querySelectorAll('circle')).toHaveLength(2)
  })

  it('colors the game dot by verdict and can hide the legend', () => {
    const { container } = render(<RangeRow rows={[row({ verdict: 'worse' }), row({ key: 'b', verdict: 'neutral' })]} format={f} legend={false} />)
    const circles = [...container.querySelectorAll('circle')].filter((c) => c.getAttribute('r') === '5.5')
    expect(circles.map((c) => c.getAttribute('fill'))).toEqual(['var(--critical)', 'var(--text-muted)'])
    expect(screen.queryByText('Typical range')).not.toBeInTheDocument()
  })

  it('handles null game values', () => {
    const { container } = render(<RangeRow rows={[row({ game: null })]} format={f} />)
    expect(container.textContent).not.toContain('vs season')
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('no data'))
  })

  it('the game dot slides from the season dot but is drawn at its own value', () => {
    const { container } = render(<RangeRow rows={[row({})]} format={f} legend={false} />)
    const [season, game] = [...container.querySelectorAll('circle')]
    expect(game).toHaveClass('dot-slide')
    expect(season).not.toHaveClass('dot-slide')
    const dx = Number(season.getAttribute('cx')) - Number(game.getAttribute('cx'))
    expect(Number.parseFloat((game as unknown as SVGElement).style.getPropertyValue('--from-x'))).toBeCloseTo(dx)
    expect(Number(game.getAttribute('cx'))).toBeGreaterThan(Number(season.getAttribute('cx')))
  })
})
