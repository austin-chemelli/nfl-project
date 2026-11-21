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

  it('puts the math in the Method page and keeps both betting pages out of the nav', async () => {
    renderRoute('/method')
    const nav = within(await screen.findByRole('navigation', { name: 'Main' }))
    expect(await screen.findByRole('tab', { name: 'Betting math' }, { timeout: 12000 })).toBeInTheDocument()
    expect(nav.queryByRole('link', { name: /betting/i })).toBeNull()
    for (const name of ['This week', 'League', 'Tracker', 'History', 'How it works']) expect(nav.getByRole('link', { name })).toBeInTheDocument()
  })

  it('routes the unlisted card by its URL and asks search engines to skip it', async () => {
    renderRoute('/betting')
    expect(await screen.findByRole('heading', { level: 1, name: "This week's bets" })).toBeInTheDocument()
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['This week', 'Your bets', 'Track record'])
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex')
  })

  it('drops the tabs of a section set to dev', async () => {
    BETTING_VISIBILITY.log = 'dev'
    renderRoute('/betting')
    const tabs = await screen.findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['This week', 'Track record'])
  })

  it('answers like a page that does not exist when its sections are all dev', async () => {
    BETTING_VISIBILITY.card = 'dev'
    BETTING_VISIBILITY.log = 'dev'
    renderRoute('/betting')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/not found/i)
  })

  it('drops the Betting math tab of the Method page when the math is dev', async () => {
    BETTING_VISIBILITY.math = 'dev'
    renderRoute('/method')
    await screen.findAllByRole('tab')
    expect(screen.queryByRole('tab', { name: 'Betting math' })).toBeNull()
  })

  it('says what each visibility means', () => {
    expect([reachable('public'), reachable('unlisted'), reachable('dev')]).toEqual([true, true, false])
    expect([listed('public'), listed('unlisted'), listed('dev')]).toEqual([true, false, false])
  })
})

describe('in development', () => {
  it('shows every section, and the math tab links to the weekly page', async () => {
    expect([reachable('dev'), listed('dev'), listed('unlisted')]).toEqual([true, true, true])
    renderRoute('/method?tab=betting')
    expect(await screen.findByRole('link', { name: /this week.s bets/i })).toHaveAttribute('href', '/betting')
  })
})
