import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BookStrip } from './BookStrip'

const fmt = (v: number) => (v === 0 ? "pick'em" : v > 0 ? `DEN −${v}` : `KC −${-v}`)
const sides = { above: 'DEN', below: 'KC', aboveColor: 'red', belowColor: 'blue' }

describe('BookStrip', () => {
  it('stacks books on the same number and draws the key numbers between them', () => {
    const dots = [{ key: 'a', v: -1.5, label: 'A' }, { key: 'b', v: 0, label: 'B' }, { key: 'c', v: 0, label: 'C' }, { key: 'd', v: 1.5, label: 'D' }]
    const { container } = render(<BookStrip dots={dots} median={0} format={fmt} label="Spread" sides={sides} />)
    expect(container.querySelectorAll('circle')).toHaveLength(4)
    expect(container.querySelectorAll('[data-testid="key-number"]')).toHaveLength(1) // pick'em; 3 and 7 are off the scale
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', "Spread: KC −1.5 at 1, pick'em at 2, DEN −1.5 at 1; median pick'em")
  })
  it('draws nothing without books', () => {
    const { container } = render(<BookStrip dots={[]} median={null} format={fmt} label="Spread" />)
    expect(container.querySelector('svg')).toBeNull()
  })
})
