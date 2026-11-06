import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DivergingBars } from './DivergingBars'
import { MatchupBand, type MatchupBandRow } from './MatchupBand'

vi.mock('./useWidth', () => ({ useWidth: () => [() => undefined, 600] }))

describe('DivergingBars motion', () => {
  const rows = Array.from({ length: 10 }, (_, i) => ({ key: `r${i}`, label: `Row ${i}`, value: i % 2 ? -(i + 1) : i + 1 }))
  it('bars carry the motion class, anchor on the axis side, cap the stagger at 8 rows, and keep their final geometry', () => {
    const { container } = render(<DivergingBars rows={rows} format={String} />)
    const bars = [...container.querySelectorAll<SVGRectElement>('rect.bar-grow')]
    expect(bars).toHaveLength(10)
    expect(bars[0].style.transformOrigin).toBe('left')
    expect(bars[1].style.transformOrigin).toBe('right')
    expect(bars.map((b) => b.style.getPropertyValue('--i'))).toEqual(['0', '1', '2', '3', '4', '5', '6', '7', '7', '7'])
    const axis = Number(container.querySelector('line')!.getAttribute('x1'))
    expect(Number(bars[0].getAttribute('x'))).toBeCloseTo(axis) // right-going bar starts at the axis
    expect(Number(bars[1].getAttribute('x')) + Number(bars[1].getAttribute('width'))).toBeCloseTo(axis) // left-going bar ends there
    expect(Number(bars[0].getAttribute('width'))).toBeGreaterThan(1)
  })
})

describe('MatchupBand motion', () => {
  const row = (key: string): MatchupBandRow => ({ key, label: key, away: 1, home: 3, lo: 0, q1: 1, med: 2, q3: 3, hi: 4, stands: true })
  it('the league band grows out from its median', () => {
    const { container } = render(<MatchupBand rows={[row('a'), row('b')]} away="AWY" home="HME" format={String} />)
    const bands = [...container.querySelectorAll<SVGRectElement>('rect.bar-grow')]
    expect(bands).toHaveLength(4)
    expect(bands[0].style.transformOrigin).toMatch(/^\d+(\.\d+)?% 50%$/)
    expect(bands[2].style.getPropertyValue('--i')).toBe('1')
    expect(Number(screen.getAllByTestId('band')[0].getAttribute('width'))).toBeGreaterThan(2)
  })
  it('the tip card fades in', () => {
    const { container } = render(<MatchupBand rows={[row('a')]} away="AWY" home="HME" format={String} />)
    fireEvent.focus(container.querySelector('g[tabindex="0"]')!)
    expect(screen.getByTestId('chart-tip')).toHaveClass('chart-tip-in')
  })
})
