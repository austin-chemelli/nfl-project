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
    for (const name of ['This week', 'League', 'Tracker', 'History', 'Build', 'How it works']) expect(nav.getByRole('link', { name })).toBeInTheDocument()
  })

  it('answers their URLs like pages that do not exist', async () => {
    renderRoute('/coaches')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/not found|no page|doesn't exist/i)
    expect(screen.queryByText('Coaches & schemes')).toBeNull()
  })

  it('drops the League panel\'s link to Coaches and keeps the panel', async () => {
    renderRoute('/league?team=KC&tab=teams')
    const panel = await screen.findByRole('region', { name: /Kansas City Chiefs/ })
    expect(within(panel).queryByRole('link', { name: 'Scheme profile' })).toBeNull()
    expect(within(panel).getByRole('link', { name: /Wk 1 vs DEN/ })).toBeInTheDocument()
  })

  it('keeps the Season page\'s link back to Build, which is live again (M30)', async () => {
    renderRoute('/season/2025?set=yours&w=quality:70,form:30&team=PHI')
    expect(await screen.findByRole('heading', { level: 1, name: /Season view/ })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Back to Build your own' })).toBeInTheDocument()
  })

  it('hides only what is listed', () => {
    expect(isHidden('/coaches')).toBe(true)
    expect(isHidden('/build')).toBe(false)
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
