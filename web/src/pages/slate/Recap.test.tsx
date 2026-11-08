import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'
import type { WeekRecap } from '../../data/contract'
import { recapTiles } from './recapTiles'

/** A copy of the fixtures where the listed weeks' slates have a finished game, so their recap is requested. */
export function fixturesWithResults(weeks: number[]): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'slate-recap-'))
  fs.cpSync(path.resolve(import.meta.dirname, '../../test/fixtures'), root, { recursive: true })
  const base = JSON.parse(fs.readFileSync(path.join(root, 'site/slate_2026_08.json'), 'utf8'))
  for (const w of weeks) {
    const d = structuredClone(base)
    d.week = w
    d.games[0].result = { home_score: 23, away_score: 20, margin: 3 }
    fs.writeFileSync(path.join(root, `site/slate_2026_${String(w).padStart(2, '0')}.json`), JSON.stringify(d))
  }
  return root
}

const model = (id: string, kind: string, right: number, ll: number, vs: number | null, rank: number) =>
  ({ model_id: id, label: id, kind, n: 10, right, log_loss: ll, vs_market: vs, rank }) as WeekRecap['models'][number]
const recap = (over: Partial<WeekRecap> = {}): WeekRecap => ({
  schema_version: '4', season: 2026, week: 7, built_at: '', games: [], best_model: 'student', note: '', best_call: null, costliest_call: null,
  models: [
    model('student', 'approach', 7, 0.6, -0.018, 1), model('analyst', 'approach', 6, 0.64, 0.01, 2), model('sharp', 'approach', 6, 0.66, 0.03, 3),
    model('traditionalist', 'approach', 6, 0.65, -0.01, 4), model('market_baseline', 'reference', 6, 0.62, 0, 0),
  ],
  upsets: [{ game_id: 'g1', away: 'NYG', home: 'HOU', value: 0.196, sentence: '' }], misread: [], unluckiest: [],
  luckiest: [{ team: 'HOU', game_id: 'g1', luck_net: 5.6, sentence: '' }],
  ...over,
})

describe('recapTiles', () => {
  it('states the week in five tiles', () => {
    const t = recapTiles(recap())
    expect(t.map((x) => x.id)).toEqual(['best', 'market', 'right', 'upset', 'luck'])
    expect(t[0]).toMatchObject({ value: 'Student', sub: '7 of 10 right, score 0.600 (lower is better)', modelId: 'student' })
    expect(t[1]).toMatchObject({ value: 'Even with the market', sub: '2 of 4 ahead; about even on average. Confidence counts, not just picks' })
    expect(t[2]).toMatchObject({ value: '7 of 10', sub: 'Student; market 6 of 10', modelId: 'student' })
    expect(t[3]).toMatchObject({ value: 'NYG @ HOU', sub: 'winner was 20% in the market' })
    expect(t[4]).toMatchObject({ value: 'HOU', sub: '+5.6 pts of pure luck' })
  })
  it('beat / trailed by the average gap, with the direction printed', () => {
    const m = (gaps: number[]) => recap({ models: ['student', 'analyst', 'sharp', 'traditionalist'].map((id, i) => model(id, 'approach', 5, 0.6, gaps[i], i + 1)) })
    expect(recapTiles(m([-0.02, -0.02, -0.02, 0.02]))[1]).toMatchObject({ value: 'Scored better', sub: '3 of 4 ahead; 0.010 better on average. Confidence counts, not just picks' })
    // three slightly ahead and one far behind: worse on average, whatever the count says
    expect(recapTiles(m([-0.001, -0.002, -0.001, 0.1]))[1]).toMatchObject({ value: 'Scored worse', sub: '3 of 4 ahead; 0.024 worse on average. Confidence counts, not just picks' })
  })
  it('says how few games the approach tiles rest on while the week is being played', () => {
    const one = recap({ games: ['2026_09_JAX_BAL'], upsets: [] })
    const t = recapTiles(one, 14)
    for (const id of ['best', 'market', 'right']) expect(t.find((x) => x.id === id)?.sub).toMatch(/^after 1 of 14 games: /)
    expect(t.find((x) => x.id === 'upset')).toMatchObject({ value: 'None', sub: 'every favorite won' })
    // a finished week, or no count, reads as before
    expect(recapTiles(one, 1).find((x) => x.id === 'best')?.sub).not.toMatch(/^after/)
    expect(recapTiles(one).find((x) => x.id === 'best')?.sub).not.toMatch(/^after/)
  })

  it('does not call a near-even winner an upset', () => {
    const t = recapTiles(recap({ upsets: [{ game_id: 'g', away: 'A', home: 'B', value: 0.47, sentence: '' }] }))
    expect(t.find((x) => x.id === 'upset')).toMatchObject({ value: 'None', sub: 'lowest winner was 47% in the market' })
  })
})

describe('Recap', () => {
  it('shows the week-8 strip, with the full table and lists behind "Full recap"', async () => {
    renderRoute('/week/2026/8', fixturesWithResults([8]))
    const region = await screen.findByRole('region', { name: 'Week 8 recap' })
    const strip = within(region).getByRole('group', { name: 'Week 8 summary' })
    expect(within(strip).getByText('Traditionalist')).toBeInTheDocument()
    expect(within(strip).getByText('Scored worse')).toBeInTheDocument()
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

  it('lists the bold calls under the confidence line, each linked to its game', async () => {
    renderRoute('/week/2026/8', fixturesWithResults([8]))
    const region = await screen.findByRole('region', { name: 'Week 8 recap' })
    await userEvent.click(within(region).getByText('Full recap'))
    expect(within(region).getByRole('heading', { name: 'Bold calls' })).toBeInTheDocument()
    expect(within(region).getByText(/pays for confidence both ways/)).toBeInTheDocument()
    expect(within(region).getByText(/The Sharp gave Arizona Cardinals 91% and they won: 0\.60 better/)).toBeInTheDocument()
    expect(within(region).getByText(/The Student gave Green Bay Packers 72% and they lost: 0\.59 worse/)).toBeInTheDocument()
    expect(within(region).getByRole('link', { name: 'ARI @ DAL' })).toHaveAttribute('href', '/game/2026_08_ARI_DAL')
  })

  it('renders a recap without bold calls (week 5 predates them) and hides the block', async () => {
    renderRoute('/week/2026/5', fixturesWithResults([5]))
    const region = await screen.findByRole('region', { name: 'Week 5 recap' })
    await userEvent.click(within(region).getByText('Full recap'))
    expect(within(region).queryByText('Bold calls')).toBeNull()
  })

  it('asks for no recap while the week has no result', async () => {
    const seen = vi.spyOn(fs, 'existsSync')
    renderRoute('/week/2026/8')
    await screen.findByRole('link', { name: /^CAR\s*@\s*GB\s*\S/ })
    expect(screen.queryByRole('region', { name: /recap/ })).toBeNull()
    expect(seen.mock.calls.some(([f]) => String(f).includes('recap_2026_08'))).toBe(false)
    seen.mockRestore()
  })

  it('renders nothing for a week without a recap', async () => {
    renderRoute('/week/2026/9')
    await screen.findByText(/No slate for 2026 week 9/)
    expect(screen.queryByRole('region', { name: /recap/ })).toBeNull()
  })
})
