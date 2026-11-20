import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { BETTING_VISIBILITY, listed, reachable } from '../lib/bettingVisibility'
import { renderRoute } from '../test/render'

const original = { ...BETTING_VISIBILITY }

describe('betting guide visibility on the live site', () => {
  beforeEach(() => vi.stubEnv('DEV', false))
  afterEach(() => {
    vi.unstubAllEnvs()
    Object.assign(BETTING_VISIBILITY, original)
  })

  it('puts the math in the nav and keeps the card out of it', async () => {
    renderRoute('/method')
    const nav = within(await screen.findByRole('navigation', { name: 'Main' }))
    expect(nav.getByRole('link', { name: 'Betting math' })).toHaveAttribute('href', '/betting')
    expect(nav.queryByRole('link', { name: /your betting card/i })).toBeNull()
    for (const name of ['This week', 'League', 'Tracker', 'History', 'How it works']) expect(nav.getByRole('link', { name })).toBeInTheDocument()
  })

  it('serves the math page, with no link to the card', async () => {
    renderRoute('/betting')
    expect(await screen.findByRole('heading', { level: 1, name: 'Betting math' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /weekly card/i })).toBeNull()
    expect(document.querySelector('meta[name="robots"]')).toBeNull()
  })

  it('routes the unlisted card by its URL and asks search engines to skip it', async () => {
    renderRoute('/betting/week')
    expect(await screen.findByRole('heading', { level: 1, name: 'Your betting card' })).toBeInTheDocument()
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['This week', 'My bets', 'Record'])
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex')
  })

  it('drops the tabs of a section set to dev', async () => {
    BETTING_VISIBILITY.log = 'dev'
    renderRoute('/betting/week')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['This week', 'Record'])
  })

  it('answers like a page that does not exist when its sections are all dev', async () => {
    BETTING_VISIBILITY.card = 'dev'
    BETTING_VISIBILITY.log = 'dev'
    renderRoute('/betting/week')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/not found/i)
  })

  it('answers the math URL like a missing page when the math is dev, and leaves it out of the nav', async () => {
    BETTING_VISIBILITY.math = 'dev'
    renderRoute('/betting')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/not found/i)
    expect(within(screen.getByRole('navigation', { name: 'Main' })).queryByRole('link', { name: 'Betting math' })).toBeNull()
  })

  it('says what each visibility means', () => {
    expect([reachable('public'), reachable('unlisted'), reachable('dev')]).toEqual([true, true, false])
    expect([listed('public'), listed('unlisted'), listed('dev')]).toEqual([true, false, false])
  })
})

describe('in development', () => {
  it('shows every section, and the math page links to the card', async () => {
    expect([reachable('dev'), listed('dev'), listed('unlisted')]).toEqual([true, true, true])
    renderRoute('/betting')
    expect(await screen.findByRole('link', { name: /weekly card/i })).toHaveAttribute('href', '/betting/week')
  })
})
