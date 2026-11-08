import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { isHidden } from '../lib/hiddenPages'
import { renderRoute } from '../test/render'

describe('hidden pages on the live site', () => {
  beforeEach(() => vi.stubEnv('DEV', false))
  afterEach(() => vi.unstubAllEnvs())

  it('leaves them out of the nav and keeps the rest', async () => {
    renderRoute('/method')
    const nav = within(await screen.findByRole('navigation', { name: 'Main' }))
    expect(nav.queryByRole('link', { name: 'Coaches' })).toBeNull()
    expect(nav.queryByRole('link', { name: 'Build' })).toBeNull()
    for (const name of ['This week', 'League', 'Tracker', 'History', 'How it works']) expect(nav.getByRole('link', { name })).toBeInTheDocument()
  })

  it('answers their URLs like pages that do not exist', async () => {
    for (const url of ['/coaches', '/build?w=abc']) {
      const { unmount } = renderRoute(url)
      expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/not found|no page|doesn't exist/i)
      expect(screen.queryByText('Coaches & schemes')).toBeNull()
      expect(screen.queryByText('Build your own approach')).toBeNull()
      unmount()
    }
  })

  it('drops the League panel\'s link to Coaches and keeps the panel', async () => {
    renderRoute('/league?team=KC&tab=teams')
    const panel = await screen.findByRole('region', { name: /Kansas City Chiefs/ })
    expect(within(panel).queryByRole('link', { name: 'Scheme profile' })).toBeNull()
    expect(within(panel).getByRole('link', { name: /Wk 1 vs DEN/ })).toBeInTheDocument()
  })

  it('drops the Season page\'s link back to Build and keeps the page', async () => {
    renderRoute('/season/2025?set=yours&w=quality:70,form:30&team=PHI')
    expect(await screen.findByRole('heading', { level: 1, name: /Season view/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Back to Build your own' })).toBeNull()
  })

  it('hides only what is listed', () => {
    expect(isHidden('/coaches')).toBe(true)
    expect(isHidden('/build')).toBe(true)
    expect(isHidden('/season')).toBe(false)
    expect(isHidden('/tracker')).toBe(false)
  })
})

describe('in development', () => {
  it('keeps them, so they can be worked on', () => {
    expect(isHidden('/coaches')).toBe(false)
    expect(isHidden('/build')).toBe(false)
  })
})
