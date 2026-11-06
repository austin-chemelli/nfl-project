import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { showPanel, SummaryStrip, Tile } from './SummaryStrip'
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

  it('flashes the target panel after a tile click, not on load or a plain tab change', async () => {
    await new Promise((r) => setTimeout(r, 100)) // let the previous test's frame callbacks (which look up tabs in the document) run out
    const router = createMemoryRouter(
      [{ path: '/g', element: (<><SummaryStrip><Tile label="Injuries" value="2 out" tab="news" /></SummaryStrip><Tabs default="forecast" tabs={[{ id: 'forecast', label: 'Forecast', content: <p>fc</p> }, { id: 'news', label: 'News', content: <p>nw</p> }]} /></>) }],
      { initialEntries: ['/g'] },
    )
    render(<RouterProvider router={router} />)
    expect(screen.getByRole('tabpanel')).not.toHaveClass('tile-flash')
    await userEvent.click(screen.getByRole('tab', { name: 'News' }))
    await new Promise((r) => setTimeout(r, 100))
    expect(screen.getByRole('tabpanel')).not.toHaveClass('tile-flash')
    await userEvent.click(screen.getByRole('tab', { name: 'Forecast' }))
    await userEvent.click(screen.getByRole('button', { name: /Injuries/ }))
    await waitFor(() => expect(screen.getByRole('tabpanel')).toHaveClass('tile-flash'))
    expect(screen.getByRole('tabpanel')).toHaveClass('tab-panel-in')
  })

  it('waits for a panel the router mounts late, many frames after the tile click', async () => {
    const tab = document.createElement('button')
    tab.id = 'late-tab'
    tab.setAttribute('aria-controls', 'late-panel')
    document.body.append(tab)
    showPanel(tab)
    await new Promise((r) => setTimeout(r, 150)) // past the old 3-frame retry
    const panel = document.createElement('div')
    panel.id = 'late-panel'
    panel.setAttribute('aria-labelledby', 'late-tab')
    document.body.append(panel)
    await waitFor(() => expect(panel).toHaveClass('tile-flash'))
    tab.remove()
    panel.remove()
  })
})
