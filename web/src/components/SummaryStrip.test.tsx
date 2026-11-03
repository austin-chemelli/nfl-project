import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { SummaryStrip, Tile } from './SummaryStrip'
import { Tabs } from './Tabs'

describe('SummaryStrip', () => {
  it('renders tiles with label, value and sub-line', () => {
    const router = createMemoryRouter([{ path: '/', element: <SummaryStrip><Tile label="The call" value="GB 64%" sub="Market 60%" modelId="sharp" /><Tile label="Luck" value="+3 pts" /></SummaryStrip> }])
    render(<RouterProvider router={router} />)
    expect(screen.getByRole('group', { name: 'Summary' })).toBeInTheDocument()
    expect(screen.getByText('GB 64%')).toBeInTheDocument()
    expect(screen.getByText('Market 60%')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('a tile with a tab switches the tab without leaving the page', async () => {
    const router = createMemoryRouter(
      [{ path: '/g', element: (<><SummaryStrip><Tile label="Injuries" value="2 out" tab="news" /></SummaryStrip><Tabs default="forecast" tabs={[{ id: 'forecast', label: 'Forecast', content: <p>fc</p> }, { id: 'news', label: 'News', content: <p>nw</p> }]} /></>) }],
      { initialEntries: ['/g'] },
    )
    render(<RouterProvider router={router} />)
    expect(screen.getByText('fc')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Injuries/ }))
    expect(screen.getByText('nw')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/g')
    expect(router.state.location.search).toBe('?tab=news')
  })
})
