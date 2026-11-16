import fs from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { Game } from '../../data/contract'
import { GameHeader } from './Header'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site/game/2026_08_CAR_GB.json')
const base = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const withStatus = (status: 'locked' | 'preview') => ({
  ...base,
  models: Object.fromEntries(Object.entries(base.models).map(([k, m]) => [k, { ...m, status, lock_ts: '2026-11-14T17:08:51Z' }])),
})

describe('GameHeader', () => {
  it('says when a locked game was locked, in Eastern time', () => {
    render(<MemoryRouter><GameHeader g={withStatus('locked')} /></MemoryRouter>)
    expect(screen.getByTestId('locked-at').textContent).toBe('at Sat 12:08 PM ET')
  })
  it('says nothing about a lock time for a preview', () => {
    render(<MemoryRouter><GameHeader g={withStatus('preview')} /></MemoryRouter>)
    expect(screen.queryByTestId('locked-at')).toBeNull()
  })
})
