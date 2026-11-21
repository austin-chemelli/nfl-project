import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import TrackerPage from '../Tracker'
import { LinesContext, NO_LINES, type Lines } from '../../you/current'
import { stubFetch } from '../../test/render'

const you: Lines = {
  ...NO_LINES,
  status: 'ready',
  approaches: [...NO_LINES.approaches, 'you'],
  you: {
    name: 'You', points: { quality: 50, offense: 50 }, isDefault: false, savedAt: '2026-10-20T00:00:00Z',
    line: { W: { quality: 0.5, offense: 0.5 }, intercept: 0, a: 1, c: 0.1 },
    migration: { changed: false } as never,
  },
}

function renderTracker(url: string, lines: Lines) {
  stubFetch()
  const router = createMemoryRouter([{ path: '/tracker', element: <TrackerPage /> }], { initialEntries: [url] })
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <LinesContext.Provider value={lines}><RouterProvider router={router} /></LinesContext.Provider>
    </QueryClientProvider>,
  )
}

describe('Tracker "Your line" tab', () => {
  it('is absent without a saved line', async () => {
    renderTracker('/tracker?tab=you', NO_LINES)
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((x) => x.textContent)).not.toContain('Your line')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('appears last with a line and shows the unofficial record', async () => {
    renderTracker('/tracker?tab=you', you)
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.at(-1)).toHaveTextContent('Your line')
    expect((await screen.findAllByText('Picks right', {}, { timeout: 8000 })).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Since you saved/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('unofficial').length).toBeGreaterThan(0)
  })
})
