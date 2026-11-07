import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TendencyRow, type TendencyRowData } from './TendencyRow'

const row = (o: Partial<TendencyRowData>): TendencyRowData => ({ key: 'm', label: 'Motion', summary: 'Motion, 3rd', now: 0.9, past: 0.95, last: 0.3, value: '73.8%', sub: '3rd of 32', ...o })

describe('TendencyRow', () => {
  it('draws this season, the caller\'s past and last season, and prints the value', () => {
    const { container } = render(<TendencyRow rows={[row({})]} />)
    for (const id of ['this-season', 'caller-past', 'last-season']) expect(screen.getByTestId(id)).toBeInTheDocument()
    expect(container.textContent).toContain('73.8%')
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'Motion, 3rd')
  })
  it('draws only the marks it has', () => {
    render(<TendencyRow rows={[row({ now: null, past: null })]} />)
    expect(screen.queryByTestId('this-season')).not.toBeInTheDocument()
    expect(screen.queryByTestId('caller-past')).not.toBeInTheDocument()
    expect(screen.getByTestId('last-season')).toBeInTheDocument()
  })
  it('names unusual ends of the scale', () => {
    const { container } = render(<TendencyRow rows={[row({ ends: ['shorter', 'longer'] })]} />)
    expect(container.textContent).toContain('longer')
  })
})
