import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderRoute } from '../test/render'

// Smoke: every route renders inside the layout against the fixtures without throwing.
const ROUTES = ['/', '/week/2026/8', '/game/2026_08_CAR_GB', '/tracker', '/hypotheses', '/coaches', '/build', '/season/2025', '/method', '/nope']

describe('routes', () => {
  it.each([['/teams', 'Teams'], ['/history', /history/i]])('redirects %s to the nav page', async (url, title) => {
    renderRoute(url)
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
  })

  for (const url of ROUTES) {
    it(`renders ${url}`, async () => {
      renderRoute(url)
      expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
      expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
    })
  }
})
