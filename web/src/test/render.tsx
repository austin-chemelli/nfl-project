/**
 * Test helpers: render a route against the checked-in fixtures (fetch is stubbed to read
 * src/test/fixtures/site), so page tests exercise the real contract and data hooks.
 */
import fs from 'node:fs'
import path from 'node:path'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { routes } from '../app/routes'

const FIX = path.resolve(import.meta.dirname, 'fixtures')

export function stubFetch(root: string = FIX) {
  vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
    const url = String(input)
    const rel = url.replace(/^.*?\/(site|predictions)\//, '$1/')
    const file = path.join(root, rel)
    if (!fs.existsSync(file)) return new Response('not found', { status: 404 })
    return new Response(fs.readFileSync(file, 'utf8'), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}

export function renderRoute(url: string, root?: string) {
  stubFetch(root)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [url] })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}
