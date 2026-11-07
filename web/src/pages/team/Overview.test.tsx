import fs from 'node:fs'
import path from 'node:path'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import { LeagueFile, SimilarFile, TeamsFile } from '../../data/contract'
import { Overview } from './Overview'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const load = (f: string) => JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8'))
const teams = TeamsFile.parse(load('teams.json'))
const league = LeagueFile.parse(load('league.json'))
const similar = SimilarFile.parse(load('similar.json'))

afterEach(cleanup)
const show = (p: { league?: LeagueFile; similar?: SimilarFile; code?: string }) =>
  render(<MemoryRouter><Overview code={p.code ?? 'KC'} teams={teams} league={p.league} similar={p.similar} /></MemoryRouter>)
const has = (name: string) => screen.queryByRole('region', { name }) !== null

describe('Overview', () => {
  it('renders all three sections', () => {
    show({ league, similar })
    expect(has('Where they stand')).toBe(true)
    expect(has('Best and worst')).toBe(true)
    expect(has('History says')).toBe(true)
    expect(screen.getByText('Playoffs')).toBeInTheDocument()
    expect(screen.getByText('First-round bye')).toBeInTheDocument()
    expect(screen.getAllByText(/\d(st|nd|rd|th) of 32/).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /similar seasons/i })).toHaveAttribute('href', '/league?tab=similar&team=KC')
  })

  it('drops only Where they stand without the league file', () => {
    show({ similar })
    expect(has('Where they stand')).toBe(false)
    expect(has('Best and worst')).toBe(true)
    expect(has('History says')).toBe(true)
  })

  it('drops only History says without the similar file or the team entry', () => {
    show({ league })
    expect(has('Where they stand')).toBe(true)
    expect(has('Best and worst')).toBe(true)
    expect(has('History says')).toBe(false)
    cleanup()
    const none = SimilarFile.parse({ ...load('similar.json'), teams: {} })
    show({ league, similar: none })
    expect(has('History says')).toBe(false)
  })

  it('shows the final standing only once the odds are gone', () => {
    const over = LeagueFile.parse({ ...load('league.json'), odds: { student: { teams: {} }, market: { teams: {} } } })
    show({ league: over })
    expect(has('Where they stand')).toBe(true)
    expect(screen.getByText('The regular season is over.')).toBeInTheDocument()
    expect(screen.queryByText('Playoffs')).toBeNull()
  })
})
