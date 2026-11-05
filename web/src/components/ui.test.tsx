import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBox, ModelBadge, Swatch } from './ui'
import { DataError } from '../data/api'

describe('ErrorBox', () => {
  it('suggests a reload when the data no longer matches the loaded app', () => {
    render(<ErrorBox error={new DataError('site/slate_2026_08.json', 'unexpected shape: x', false, true)} />)
    expect(screen.getByText(/updated since this page was opened/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument()
  })

  it('offers a reload without the update hint for other errors', () => {
    render(<ErrorBox error={new DataError('site/slate_2026_08.json', 'HTTP 500')} />)
    expect(screen.queryByText(/updated since this page was opened/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument()
  })
})

describe('Swatch and ModelBadge', () => {
  it('draws an approach as a filled dot and a reference as a hollow dashed ring', () => {
    const { container, rerender } = render(<Swatch modelId="student" />)
    const dot = container.firstElementChild as HTMLElement
    expect(dot).toHaveAttribute('aria-hidden', 'true')
    expect(dot.style.background).toContain('--series-student')
    expect(dot.style.border).toBe('')
    rerender(<Swatch modelId="market_baseline" size={8} />)
    const ring = container.firstElementChild as HTMLElement
    expect(ring).toHaveAttribute('aria-hidden', 'true')
    expect(ring.style.border).toContain('dashed')
    expect(ring.style.border).toContain('--series-market')
    expect(ring.style.background).toBe('')
  })

  it('shows the reference tag only when asked', () => {
    const { rerender } = render(<ModelBadge modelId="elo_v0" />)
    expect(screen.queryByText('reference')).not.toBeInTheDocument()
    rerender(<ModelBadge modelId="elo_v0" reference />)
    expect(screen.getByText('reference')).toBeInTheDocument()
  })
})
