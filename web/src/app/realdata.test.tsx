import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderRoute } from '../test/render'

// Smoke against the full local data (skipped in CI): final games, injuries, every season, the
// whole build-your-own matrix. The fixtures can't cover these, so this catches shape surprises.
const REAL = path.resolve(import.meta.dirname, '../../../data/marts')
const has = fs.existsSync(path.join(REAL, 'site', 'meta.json'))

const ROUTES = [
  ['/week/2026/1', /ARI/],
  ['/game/2026_01_ARI_LAC', /Injur/i],
  ['/game/2026_08_CAR_GB', /narrative|saying/i],
  ['/tracker', /market/i],
  ['/hypotheses', /history/i],
  ['/coaches?team=GB', /GB|Green Bay/],
  ['/build', /budget|points/i],
  ['/season/2015', /2015/],
  ['/method', /freshness|Fresh/i],
] as const

describe.skipIf(!has)('real data smoke', () => {
  for (const [url, text] of ROUTES) {
    it(`renders ${url}`, async () => {
      renderRoute(url, REAL)
      expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
      expect((await screen.findAllByText(text, {}, { timeout: 8000 })).length).toBeGreaterThan(0)
      expect(screen.queryByRole('alert')).toBeNull()
    }, 20000)
  }
})
