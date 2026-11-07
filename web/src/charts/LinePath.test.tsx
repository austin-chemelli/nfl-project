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
    const { container } = render(<LinePath points={pts} format={(v) => `${v}`} up="toward BAL" down="toward JAX" label="Spread" domain={[0, 24]} />)
    expect(container.textContent).toContain('2.5')
    expect(container.textContent).toContain('-10')
    expect(container.textContent).toContain('toward JAX')
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'Spread: 2.5 at first, -10 latest')
  })
  it('draws lock marks and numbered events', () => {
    const { container } = render(<LinePath points={pts} marks={[{ t: 15, label: 'Locked' }]} events={[{ t: 12, n: 1 }]} format={(v) => `${v}`} up="u" down="d" label="Spread" domain={[0, 24]} />)
    expect(container.textContent).toContain('Locked')
    expect(container.querySelectorAll('text')).not.toHaveLength(0)
  })
  it('draws nothing without a value', () => {
    const { container } = render(<LinePath points={[{ t: 0, v: null, note: '' }]} format={(v) => `${v}`} up="u" down="d" label="S" domain={[0, 1]} />)
    expect(container.querySelector('svg')).toBeNull()
  })
})

describe('stagger', () => {
  it('lifts a mark that would overlap the one before it, and drops back when there is room', () => {
    expect(stagger([10, 20, 24, 100])).toEqual([0, 1, 2, 0])
    expect(stagger([10, 40])).toEqual([0, 0])
  })
})

