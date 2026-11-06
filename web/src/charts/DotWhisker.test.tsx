import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DotWhisker } from './DotWhisker'

vi.mock('./useWidth', () => ({ useWidth: () => [() => undefined, 600] }))

describe('DotWhisker', () => {
  it('keeps the marker on the scale when every row sits to one side of it', () => {
    render(<DotWhisker rows={[{ key: 'a', label: 'A', value: 0.05, lo: 0.04, hi: 0.06 }]} format={String} marker={{ value: -0.03, label: 'no edge' }} />)
    const x = Number(screen.getByText(/no edge/).getAttribute('x'))
    expect(x).toBeGreaterThanOrEqual(170)
  })

  it('names the reference in a row tip, since the rows cover its own hit area', () => {
    const { container } = render(<DotWhisker rows={[{ key: 'a', label: 'Rest', value: 0.05, lo: 0.04, hi: 0.08 }]} format={String} refLabel="No effect" />)
    fireEvent.focus(container.querySelector('[role="group"]')!)
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('No effect')
  })

  it('can leave a long list out of the tab order, with each row still named', () => {
    const { container } = render(<DotWhisker focusable={false} rows={[{ key: 'a', label: 'Rest', value: 0.05, lo: 0.04, hi: 0.08, title: 'Rest: a sentence' }]} format={String} />)
    const row = container.querySelector('[role="group"]')!
    expect(row).toHaveAttribute('tabindex', '-1')
    expect(row).toHaveAttribute('aria-label', 'Rest: a sentence')
  })

  it('shows a tip on focus instead of a <title>', () => {
    const { container } = render(<DotWhisker rows={[{ key: 'a', label: 'Rest', value: 0.05, lo: 0.04, hi: 0.08 }]} format={String} refLabel="No effect" />)
    expect(container.querySelectorAll('title')).toHaveLength(0)
    expect(screen.queryByTestId('chart-tip')).not.toBeInTheDocument()
    const stops = container.querySelectorAll('svg g[tabindex="0"]')
    fireEvent.focus(stops[1])
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('Rest')
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('0.05')
    fireEvent.focus(stops[0])
    expect(screen.getByTestId('chart-tip')).toHaveTextContent('No effect')
  })
})
