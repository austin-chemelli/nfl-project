import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ExpectRow, type ExpectRowData } from './ExpectRow'

const row = (o: Partial<ExpectRowData>): ExpectRowData => ({ key: 'm', label: 'Motion', summary: 'Motion, 3rd', expected: 0.6, miss: 0.2, rough: false, observed: 0.9, last: 0.3, value: '73.8%', sub: '3rd of 32', ...o })

describe('ExpectRow', () => {
  it('draws the range, both dots and the last season, and prints the value', () => {
    const { container } = render(<ExpectRow rows={[row({})]} />)
    for (const id of ['expected-range', 'expected-dot', 'so-far-dot', 'last-season']) expect(screen.getByTestId(id)).toBeInTheDocument()
    expect(container.textContent).toContain('73.8%')
    expect(container.textContent).toContain('3rd of 32')
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'Motion, 3rd')
  })

  it('a prediction has no so-far dot', () => {
    render(<ExpectRow rows={[row({ observed: null })]} />)
    expect(screen.queryByTestId('so-far-dot')).not.toBeInTheDocument()
    expect(screen.getByTestId('expected-dot')).toBeInTheDocument()
  })

  it('with no measured miss there is no range', () => {
    render(<ExpectRow rows={[row({ miss: null })]} />)
    expect(screen.queryByTestId('expected-range')).not.toBeInTheDocument()
  })

  it('a rough guess is dashed, so it does not rest on shade alone', () => {
    render(<ExpectRow rows={[row({ rough: true })]} />)
    expect(screen.getByTestId('expected-range')).toHaveAttribute('stroke-dasharray', '3 3')
  })

  it('names unusual ends of the scale', () => {
    const { container } = render(<ExpectRow rows={[row({ ends: ['shorter', 'longer'] })]} />)
    expect(container.textContent).toContain('shorter')
    expect(container.textContent).toContain('longer')
  })
})
