import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ProbStrip, type ProbModel } from './ProbStrip'

const models: ProbModel[] = [
  { id: 'traditionalist', label: 'Traditionalist', p: 0.55 },
  { id: 'analyst', label: 'Analyst', p: 0.62 },
  { id: 'sharp', label: 'Sharp', p: 0.7 },
  { id: 'student', label: 'Student', p: 0.48 },
  { id: 'market_baseline', label: 'Market', p: 0.59 },
  { id: 'elo_v0', label: 'Elo', p: 0.6, reference: true },
]

describe('ProbStrip', () => {
  it('expanded: 6 model dots, a market line, ticks, and an aria-label with every value', () => {
    const { container } = render(<ProbStrip models={models} market={0.61} home="GB" />)
    expect(screen.getAllByTestId('dot')).toHaveLength(6)
    expect(screen.getByTestId('market')).toBeInTheDocument()
    for (const t of ['0%', '25%', '50%', '75%', '100%']) expect(container.textContent).toContain(t)
    const label = screen.getByRole('img').getAttribute('aria-label')!
    expect(label).toContain('market 61%')
    for (const m of models) expect(label).toContain(m.label)
    expect(label).toContain('Sharp 70%')
  })

  it('reference models are hollow', () => {
    render(<ProbStrip models={models} market={null} home="GB" />)
    const dots = screen.getAllByTestId('dot')
    expect(dots[5]).toHaveAttribute('fill', 'var(--surface-1)')
    expect(dots[2]).toHaveAttribute('fill', 'var(--series-sharp)')
    expect(screen.queryByTestId('market')).not.toBeInTheDocument()
  })

  it('compact: one 20px row, no axis labels', () => {
    const { container } = render(<ProbStrip models={models} market={0.61} home="GB" compact />)
    expect(container.querySelector('svg')).toHaveAttribute('height', '20')
    expect(container.querySelectorAll('text')).toHaveLength(0)
    expect(screen.getAllByTestId('dot')).toHaveLength(6)
    expect(screen.getAllByTestId('dot')[0]).toHaveAttribute('r', '4')
  })

  it('expanded dots carry the motion class and sit at their final x, with the offset in --from-x', () => {
    render(<ProbStrip models={models} market={0.61} home="GB" />)
    const dots = screen.getAllByTestId('dot')
    const mkt = Number(screen.getByTestId('market').getAttribute('x1'))
    for (const d of dots) {
      expect(d).toHaveClass('dot-slide')
      const cx = Number(d.getAttribute('cx'))
      expect(Number.parseFloat(d.style.getPropertyValue('--from-x'))).toBeCloseTo(mkt - cx)
    }
    expect(Number(dots[2].getAttribute('cx'))).toBeGreaterThan(Number(dots[0].getAttribute('cx')))
  })

  it('compact carries no motion class and keeps its title', () => {
    const { container } = render(<ProbStrip models={models} market={0.61} home="GB" compact />)
    expect(container.querySelector('.dot-slide')).toBeNull()
    expect(container.querySelectorAll('title')).toHaveLength(6)
  })

  it('shows a tip on focus with the value, and no <title> when expanded', () => {
    const { container } = render(<ProbStrip models={models} market={0.61} home="GB" />)
    expect(container.querySelectorAll('title')).toHaveLength(0)
    expect(screen.queryByTestId('chart-tip')).not.toBeInTheDocument()
    fireEvent.focus(container.querySelectorAll('svg g[tabindex="0"]')[2])
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('Sharp: GB')
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('70.0%')
  })
})
