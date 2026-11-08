import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LinePath, stagger } from './LinePath'

const pts = [
  { t: 0, v: 2.5, note: 'Tue' },
  { t: 10, v: null, note: 'Wed' },
  { t: 20, v: -10, note: 'Sat' },
]

describe('LinePath', () => {
  it('prints the first and latest values and labels the scale', () => {
    const { container } = render(<LinePath points={pts} format={(v) => `${v}`} label="Spread" domain={[0, 24]} />)
    expect(container.textContent).toContain('2.5')
    expect(container.textContent).toContain('-10')
    expect(container.textContent).toContain('0') // gridlines are labelled
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'Spread: 2.5 at first, -10 latest')
  })
  it('draws lock marks and numbered events', () => {
    const { container } = render(<LinePath points={pts} marks={[{ t: 15, label: 'Locked' }]} events={[{ t: 12, n: 1 }]} format={(v) => `${v}`} label="Spread" domain={[0, 24]} />)
    expect(container.textContent).toContain('Locked')
    expect(container.querySelectorAll('text')).not.toHaveLength(0)
  })
  it('with sides, labels gridlines in the format and draws pick\'em when the line comes near it', () => {
    const fmt = (v: number) => (v === 0 ? "pick'em" : v > 0 ? `BAL −${v}` : `JAX −${-v}`)
    const sides = { above: 'BAL', below: 'JAX', aboveColor: 'red', belowColor: 'blue' }
    const near = render(<LinePath points={[{ t: 0, v: 2.5, note: '' }, { t: 9, v: 1, note: '' }]} format={fmt} label="Spread" domain={[0, 10]} sides={sides} />)
    expect(near.container.textContent).toContain("pick'em")
    near.unmount()
    const far = render(<LinePath points={[{ t: 0, v: -7, note: '' }, { t: 9, v: -7.25, note: '' }]} format={fmt} label="Spread" domain={[0, 10]} sides={sides} />)
    expect(far.container.textContent).not.toContain("pick'em")
    expect(far.container.textContent).toContain('JAX −7.5')
  })
  it('draws nothing without a value', () => {
    const { container } = render(<LinePath points={[{ t: 0, v: null, note: '' }]} format={(v) => `${v}`} label="S" domain={[0, 1]} />)
    expect(container.querySelector('svg')).toBeNull()
  })
})

describe('stagger', () => {
  it('lifts a mark that would overlap the one before it, and drops back when there is room', () => {
    expect(stagger([10, 20, 24, 100])).toEqual([0, 1, 2, 0])
    expect(stagger([10, 40])).toEqual([0, 0])
  })
})

