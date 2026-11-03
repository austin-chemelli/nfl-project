import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'
import type { WeekRecap } from '../../data/contract'
import { recapTiles } from './recapTiles'

const model = (id: string, kind: string, right: number, ll: number, vs: number | null, rank: number) =>
  ({ model_id: id, label: id, kind, n: 10, right, log_loss: ll, vs_market: vs, rank }) as WeekRecap['models'][number]
const recap = (over: Partial<WeekRecap> = {}): WeekRecap => ({
  schema_version: '2', season: 2026, week: 7, built_at: '', games: [], best_model: 'student', note: '',
  models: [
    model('student', 'approach', 7, 0.6, -0.018, 1), model('analyst', 'approach', 6, 0.64, 0.01, 2), model('sharp', 'approach', 6, 0.66, 0.03, 3),
    model('traditionalist', 'approach', 6, 0.65, -0.01, 4), model('ensemble', 'ensemble', 7, 0.62, -0.005, 5), model('market_baseline', 'reference', 6, 0.62, 0, 0),
  ],
  upsets: [{ game_id: 'g1', away: 'NYG', home: 'HOU', value: 0.196, sentence: '' }], misread: [], unluckiest: [],
  luckiest: [{ team: 'HOU', game_id: 'g1', luck_net: 5.6, sentence: '' }],
  ...over,
})

describe('recapTiles', () => {
  it('states the week in five tiles', () => {
    const t = recapTiles(recap())
    expect(t.map((x) => x.id)).toEqual(['best', 'market', 'right', 'upset', 'luck'])
    expect(t[0]).toMatchObject({ value: 'Student', sub: '7 of 10 right, log loss 0.600', modelId: 'student' })
    expect(t[1]).toMatchObject({ value: 'Even with the market', sub: '2 of 4 ahead; about even on average' })
    expect(t[2]).toMatchObject({ value: '7 of 10', sub: 'ensemble; market 6 of 10' })
    expect(t[3]).toMatchObject({ value: 'NYG @ HOU', sub: 'winner was 20% in the market' })
    expect(t[4]).toMatchObject({ value: 'HOU', sub: '+5.6 pts of pure luck' })
  })
  it('beat / trailed by the average gap, with the direction printed', () => {
    const m = (gaps: number[]) => recap({ models: ['student', 'analyst', 'sharp', 'traditionalist'].map((id, i) => model(id, 'approach', 5, 0.6, gaps[i], i + 1)) })
    expect(recapTiles(m([-0.02, -0.02, -0.02, 0.02]))[1]).toMatchObject({ value: 'Beat the market', sub: '3 of 4 ahead; 0.010 log loss better on average' })
    // three slightly ahead and one far behind: worse on average, whatever the count says
    expect(recapTiles(m([-0.001, -0.002, -0.001, 0.1]))[1]).toMatchObject({ value: 'Trailed the market', sub: '3 of 4 ahead; 0.024 log loss worse on average' })
  })
  it('does not call a near-even winner an upset', () => {
    const t = recapTiles(recap({ upsets: [{ game_id: 'g', away: 'A', home: 'B', value: 0.47, sentence: '' }] }))
    expect(t.find((x) => x.id === 'upset')).toMatchObject({ value: 'None', sub: 'lowest winner was 47% in the market' })
  })
})

describe('Recap', () => {
  it('shows the week-8 strip, with the full table and lists behind "Full recap"', async () => {
    renderRoute('/week/2026/8')
    const region = await screen.findByRole('region', { name: 'Week 8 recap' })
    const strip = within(region).getByRole('group', { name: 'Week 8 summary' })
    expect(within(strip).getByText('Traditionalist')).toBeInTheDocument()
    expect(within(strip).getByText('Trailed the market')).toBeInTheDocument()
    expect(within(strip).getByText('CAR @ GB')).toBeInTheDocument()
    expect(within(strip).getByText('CAR')).toBeInTheDocument()
    const details = within(region).getByText('Full recap').closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    await userEvent.click(within(region).getByText('Full recap'))
    expect(within(details).getByText('0.612')).toBeInTheDocument()
    expect(within(details).getAllByRole('link', { name: 'CAR @ GB' })[0]).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    expect(within(details).getByRole('link', { name: 'GB' })).toHaveAttribute('href', '/game/2026_08_CAR_GB')
    expect(within(details).getByText(/rank here says almost nothing/)).toBeInTheDocument()
  })

  it('renders nothing for a week without a recap', async () => {
    renderRoute('/week/2026/9')
    await screen.findByText(/No slate for 2026 week 9/)
    expect(screen.queryByRole('region', { name: /recap/ })).toBeNull()
  })
})
