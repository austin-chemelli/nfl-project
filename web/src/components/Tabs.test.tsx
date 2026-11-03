import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { Tabs } from './Tabs'

function Probe() {
  const l = useLocation()
  return <div data-testid="loc">{l.search}</div>
}

function setup(url = '/g', def = 'b') {
  const router = createMemoryRouter(
    [{ path: '/g', element: (<><Tabs default={def} label="Sections" tabs={[
      { id: 'a', label: 'Alpha', content: <p>panel a</p> },
      { id: 'b', label: 'Beta', content: <p>panel b</p> },
      { id: 'c', label: 'Gamma', content: <p>panel c</p> },
    ]} /><Probe /></>) }],
    { initialEntries: [url] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('Tabs', () => {
  it('uses the default and renders only the active panel', () => {
    setup()
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('panel b')).toBeInTheDocument()
    expect(screen.queryByText('panel a')).not.toBeInTheDocument()
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', screen.getByRole('tab', { name: 'Beta' }).id)
  })

  it('reads ?tab=', () => {
    setup('/g?tab=c')
    expect(screen.getByText('panel c')).toBeInTheDocument()
  })

  it('falls back to the default for an unknown tab', () => {
    setup('/g?tab=nope')
    expect(screen.getByText('panel b')).toBeInTheDocument()
  })

  it('writes the URL on click, replacing history', async () => {
    const r = setup()
    await userEvent.click(screen.getByRole('tab', { name: 'Gamma' }))
    expect(screen.getByTestId('loc')).toHaveTextContent('?tab=c')
    expect(r.state.historyAction).toBe('REPLACE')
    expect(screen.getByText('panel c')).toBeInTheDocument()
  })

  it('has roving tabindex and arrow/Home/End keys that wrap', async () => {
    setup('/g', 'a')
    const tab = (n: string) => screen.getByRole('tab', { name: n })
    expect(tab('Alpha')).toHaveAttribute('tabindex', '0')
    expect(tab('Beta')).toHaveAttribute('tabindex', '-1')
    tab('Alpha').focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(tab('Gamma')).toHaveFocus()
    expect(tab('Gamma')).toHaveAttribute('aria-selected', 'true')
    await userEvent.keyboard('{ArrowRight}')
    expect(tab('Alpha')).toHaveFocus()
    await userEvent.keyboard('{End}')
    expect(tab('Gamma')).toHaveFocus()
    await userEvent.keyboard('{Home}')
    expect(tab('Alpha')).toHaveFocus()
  })
})
