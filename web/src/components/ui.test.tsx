import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { UseQueryResult } from '@tanstack/react-query'
import { ErrorBox, Loaded, Loading, ModelBadge, Page, PageSkeleton, Skeleton, Swatch } from './ui'
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

describe('Page document title', () => {
  it('uses the title, a docTitle, or just the site name', () => {
    const { rerender } = render(<Page title="Tracker">x</Page>)
    expect(document.title).toBe('Tracker · NFL approaches')
    rerender(<Page title={<span>CAR @ GB</span>} docTitle="CAR @ GB, Week 8">x</Page>)
    expect(document.title).toBe('CAR @ GB, Week 8 · NFL approaches')
    rerender(<Page title={<span>Game</span>}>x</Page>)
    expect(document.title).toBe('NFL approaches')
  })
})

describe('skeletons', () => {
  it('Skeleton pulses only under motion-safe', () => {
    const { container } = render(<Skeleton className="h-4" />)
    const el = container.firstElementChild as HTMLElement
    expect(el).toHaveAttribute('aria-hidden', 'true')
    expect(el.className).toContain('motion-safe:animate-pulse')
    expect(el.className.split(/\s+/)).not.toContain('animate-pulse')
  })

  it('PageSkeleton is a labelled status with tiles, tabs and blocks, and no bare animate-pulse', () => {
    const { container } = render(<PageSkeleton what="game" shape="game" />)
    expect(screen.getByRole('status', { name: 'Loading game…' })).toBeInTheDocument()
    expect(screen.getByText('Loading game…')).toHaveClass('sr-only')
    expect(container.querySelectorAll('[data-skeleton="tile"]')).toHaveLength(5)
    expect(container.querySelector('[data-skeleton="tabs"]')).not.toBeNull()
    expect(container.querySelectorAll('.motion-safe\\:animate-pulse').length).toBeGreaterThan(5)
    expect(container.innerHTML.replace(/motion-safe:animate-pulse/g, '')).not.toContain('animate-pulse')
  })

  it('cards is the card blocks alone, for a section under a page that already has its tiles', () => {
    const { container } = render(<PageSkeleton shape="cards" title={false} />)
    expect(container.querySelectorAll('[data-skeleton="card"]').length).toBeGreaterThan(1)
    expect(container.querySelector('[data-skeleton="tile"]')).toBeNull()
    expect(container.querySelector('[data-skeleton="tabs"]')).toBeNull()
  })
  it('slate has cards and no tab bar; tracker has tabs and one chart block', () => {
    const slate = render(<PageSkeleton shape="slate" />)
    expect(slate.container.querySelectorAll('[data-skeleton="card"]').length).toBeGreaterThan(1)
    expect(slate.container.querySelector('[data-skeleton="tabs"]')).toBeNull()
    slate.unmount()
    const tr = render(<PageSkeleton shape="tracker" />)
    expect(tr.container.querySelector('[data-skeleton="tabs"]')).not.toBeNull()
  })

  it('Loading what="page" renders the page shape with a title bar', () => {
    const { container } = render(<Loading what="page" />)
    expect(screen.getByRole('status', { name: 'Loading page…' })).toBeInTheDocument()
    expect(container.querySelector('[data-skeleton="tabs"]')).not.toBeNull()
  })

  it('a small Loaded caller gets the compact form, and a shaped one the page shape', () => {
    const pending = { isPending: true, isError: false } as UseQueryResult<number>
    const small = render(<Loaded q={pending} what="method">{() => null}</Loaded>)
    expect(screen.getByRole('status', { name: 'Loading method…' })).toBeInTheDocument()
    expect(small.container.querySelector('[data-skeleton="tile"]')).toBeNull()
    small.unmount()
    const shaped = render(<Loaded q={pending} what="game" shape="game">{() => null}</Loaded>)
    expect(shaped.container.querySelectorAll('[data-skeleton="tile"]')).toHaveLength(5)
  })
})
