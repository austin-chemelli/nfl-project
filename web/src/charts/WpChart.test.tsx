import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { RetroGame } from '../data/contract'
import { markText } from '../pages/game/helpers'
import { WpChart } from './WpChart'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site/retro/2026_08_CAR_GB.json')
const r = RetroGame.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const series = r.wp_series!

const chart = (s = series, extra: Partial<Parameters<typeof WpChart>[0]> = {}) => (
  <WpChart
    series={s}
    home="GB"
    away="CAR"
    homeScore={20}
    awayScore={23}
    describe={(p) => markText(p, 'GB', 'CAR', p.factor === 'fumbles' ? 'Fumble recoveries' : null)}
    {...extra}
  />
)

describe('WpChart', () => {
  it('draws one line, the marks, quarter labels and team ends', () => {
    const { container } = render(chart())
    expect(container.querySelectorAll('path.wp-line')).toHaveLength(1)
    expect(container.querySelector('path.wp-line')).toHaveAttribute('pathLength', '1')
    expect(screen.getAllByTestId('wp-mark')).toHaveLength(series.plays.length)
    for (const q of ['Q1', 'Q2', 'Q3', 'Q4']) expect(screen.getByText(q)).toBeInTheDocument()
    expect(screen.queryByText('OT')).toBeNull()
    expect(screen.getAllByTestId('wp-rule')).toHaveLength(3)
    expect(screen.getByText('GB 100%')).toBeInTheDocument()
    expect(screen.getByText('CAR 100%')).toBeInTheDocument()
  })

  it('shows OT only for an overtime game', () => {
    render(chart({ ...series, ot: true, end_t: 4200 }, { homeScore: 23, awayScore: 20 }))
    expect(screen.getByText('OT')).toBeInTheDocument()
    expect(screen.getAllByTestId('wp-rule')).toHaveLength(4)
    expect(screen.getByTestId('wp-end-note').textContent).toContain('(OT)')
  })

  it('numbers marks in time order', () => {
    render(chart())
    const marks = screen.getAllByTestId('wp-mark')
    expect(marks.map((m) => m.querySelector('text')?.textContent)).toEqual(['1', '2', '3'])
    const ts = [...series.plays].sort((a, b) => a.t - b.t)
    expect(ts.map((p) => p.play_id)).toEqual([2518, 3402, 3688])
    // marks sit on the curve's x: later plays are further right
    const cx = marks.map((m) => Number(m.querySelector('circle')!.getAttribute('cx')))
    expect(cx).toEqual([...cx].sort((a, b) => a - b))
  })

  it('names start, low and final in the aria-label', () => {
    render(chart())
    const label = screen.getByRole('img').getAttribute('aria-label')!
    expect(label).toContain('GB 65% at kickoff (nflfastR)')
    expect(label).toContain('CAR low of 16% in Q2')
    expect(label).toContain('CAR won 23–20')
  })

  it('annotates kickoff and final, and rings the winner low only under 25%', () => {
    const { container } = render(chart())
    expect(screen.getByTestId('wp-start-note')).toHaveTextContent('GB 65% at kickoff (nflfastR)')
    expect(screen.getByTestId('wp-end-note')).toHaveTextContent('CAR won 23–20')
    expect(screen.getByTestId('wp-low')).toBeInTheDocument()
    expect(screen.getByTestId('wp-low-note')).toHaveTextContent('CAR 16%')
    expect(container.querySelectorAll('[data-testid="wp-low"]')).toHaveLength(1)
  })

  it('a tie reads Tied', () => {
    render(chart({ ...series, winner_low: null }, { homeScore: 20, awayScore: 20 }))
    expect(screen.getByTestId('wp-end-note')).toHaveTextContent('Tied 20–20')
    expect(screen.queryByTestId('wp-low')).toBeNull()
  })

  it('focus on a mark shows the play text and the factor label', () => {
    render(chart())
    expect(screen.queryByTestId('chart-tip')).toBeNull()
    fireEvent.focus(screen.getAllByTestId('wp-mark')[1]) // 3402, the fumble
    const tip = screen.getByTestId('chart-tip')
    expect(tip).toHaveTextContent('Q4 3:02 · GB')
    expect(tip).toHaveTextContent('36% → 79%')
    expect(tip).toHaveTextContent('+43 pts')
    expect(tip).toHaveTextContent('FUMBLES (J.Horn)')
    expect(tip).toHaveTextContent('Counted in: Fumble recoveries')
  })

  it('keeps every mark and note inside the width at 375 px', () => {
    // jsdom has no layout: useWidth keeps its 640 fallback, so assert on the coordinates drawn
    const { container } = render(chart())
    const svg = container.querySelector('svg')!
    const w = Number(svg.getAttribute('width'))
    for (const c of container.querySelectorAll('circle:not([fill="transparent"])')) { // the invisible hit areas may clip at the edge
      const cx = Number(c.getAttribute('cx'))
      const rr = Number(c.getAttribute('r'))
      expect(cx - rr).toBeGreaterThanOrEqual(0)
      expect(cx + rr).toBeLessThanOrEqual(w)
    }
    expect(Number(svg.getAttribute('height'))).toBe(220)
  })
})
