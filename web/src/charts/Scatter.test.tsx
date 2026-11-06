import { fireEvent, render, screen } from '@testing-library/react'
import type { CSSProperties } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Scatter, type ScatterProps } from './Scatter'

vi.mock('./useWidth', () => ({ useWidth: () => [() => undefined, 600] }))

const CODES = Array.from({ length: 32 }, (_, i) => `${String.fromCharCode(65 + (i % 26))}${String.fromCharCode(65 + ((i * 7) % 26))}${i}`)
const points = CODES.map((c, i) => ({ key: c, label: c, x: i, y: (i * 5) % 11, tone: i % 2 ? ('conf-afc' as const) : ('conf-nfc' as const) }))
const fmt = (v: number) => v.toFixed(1)

function setup(extra: Partial<ScatterProps> = {}) {
  const props: ScatterProps = {
    points,
    x: { title: 'Offense', format: fmt, mean: 15 },
    y: { title: 'Defense', format: fmt, mean: 5 },
    label: 'Teams',
    tip: (k) => <span>tip for {k}</span>,
    ...extra,
  }
  return render(<Scatter {...props} />)
}

const pt = (k: string) => document.querySelector(`[data-key="${k}"]`) as SVGGElement
const cx = (k: string) => Number(pt(k).querySelector('circle:last-child')!.getAttribute('cx'))
const cy = (k: string) => Number(pt(k).querySelector('circle:last-child')!.getAttribute('cy'))

describe('Scatter', () => {
  it('has 32 focus stops in the order given', () => {
    setup()
    const stops = screen.getAllByTestId('point')
    expect(stops).toHaveLength(32)
    expect(stops.map((s) => s.getAttribute('data-key'))).toEqual(CODES)
    expect(stops.every((s) => s.getAttribute('tabindex') === '0')).toBe(true)
  })

  it('lists every point with both values in the aria-label', () => {
    setup()
    const text = screen.getByRole('img').getAttribute('aria-label')!
    expect(text.startsWith('Teams')).toBe(true)
    for (const p of points) expect(text).toContain(`${p.label}, Offense ${fmt(p.x)}, Defense ${fmt(p.y)}`)
  })

  it('puts the lowest value at the right and top on a flipped axis', () => {
    setup({ x: { title: 'X', format: fmt, flip: true }, y: { title: 'Y', format: fmt, flip: true } })
    expect(cx(CODES[0])).toBeGreaterThan(cx(CODES[31]))
    expect(cy(CODES[0])).toBeLessThan(cy(CODES[1]))
    // lowest y is at the top
    const lowY = points.find((p) => p.y === 0)!.key
    const highY = points.find((p) => p.y === 10)!.key
    expect(cy(lowY)).toBeLessThan(cy(highY))
  })

  it('puts the lowest value at the left and bottom otherwise', () => {
    setup()
    expect(cx(CODES[0])).toBeLessThan(cx(CODES[31]))
    const lowY = points.find((p) => p.y === 0)!.key
    const highY = points.find((p) => p.y === 10)!.key
    expect(cy(lowY)).toBeGreaterThan(cy(highY))
  })

  it('adds the direction to a title only when the axis has one', () => {
    const { unmount } = setup()
    expect(screen.queryByText(/better/)).toBeNull()
    unmount()
    setup({ x: { title: 'Offense', format: fmt, better: true }, y: { title: 'Defense', format: fmt, better: true } })
    expect(screen.getByText(/Offense · better →/)).toBeTruthy()
    expect(screen.getByText(/↑ better · Defense/)).toBeTruthy()
  })

  it('draws a dashed mean line per axis that has one', () => {
    setup()
    expect(screen.getByTestId('mean-x').getAttribute('stroke-dasharray')).toBeTruthy()
    expect(screen.getByTestId('mean-y')).toBeTruthy()
  })

  it('draws the four quadrant captions', () => {
    setup({ quadrants: ['Top left', 'Top right', 'Bottom left', 'Bottom right'] })
    expect(screen.getAllByTestId('quadrant')).toHaveLength(4)
    expect(screen.getByText('Top left')).toBeTruthy()
  })

  it('shows chart-tip on hover and on focus', () => {
    setup()
    expect(screen.queryByTestId('chart-tip')).toBeNull()
    fireEvent.pointerMove(pt('AA0'), { clientX: 50, clientY: 50 })
    expect(screen.getByTestId('chart-tip').textContent).toContain('tip for AA0')
    fireEvent.pointerLeave(pt('AA0'))
    expect(screen.queryByTestId('chart-tip')).toBeNull()
    fireEvent.focus(pt(CODES[3]))
    expect(screen.getByTestId('chart-tip').textContent).toContain(`tip for ${CODES[3]}`)
  })

  it('calls onSelect on click and on Enter', () => {
    const onSelect = vi.fn()
    setup({ onSelect })
    fireEvent.click(pt(CODES[4]))
    fireEvent.keyDown(pt(CODES[5]), { key: 'Enter' })
    expect(onSelect.mock.calls).toEqual([[CODES[4]], [CODES[5]]])
  })

  it('rings and labels the selected point, last in the drawing order', () => {
    setup({ selected: CODES[10] })
    const sel = screen.getByTestId('selected')
    expect(sel.textContent).toBe(CODES[10])
    expect(sel.parentElement!.lastElementChild).toBe(sel)
  })

  it('labels a hovered point', () => {
    setup()
    fireEvent.pointerMove(pt(CODES[12]), { clientX: 50, clientY: 50 })
    expect(screen.getByTestId('hovered').textContent).toBe(CODES[12])
  })

  it('maps tones to CSS variables', () => {
    setup({ points: [
      { key: 'a', label: 'A', x: 1, y: 1, tone: 'conf-afc' },
      { key: 'b', label: 'B', x: 2, y: 2, tone: 'conf-nfc' },
      { key: 'c', label: 'C', x: 3, y: 3, tone: 'strong' },
      { key: 'd', label: 'D', x: 4, y: 4, tone: 'muted' },
    ] })
    const fill = (k: string) => pt(k).querySelector('circle:last-child')!.getAttribute('fill')
    expect(fill('a')).toBe('var(--conf-afc)')
    expect(fill('b')).toBe('var(--conf-nfc)')
    expect(fill('c')).toBe('var(--text-primary)')
    expect(fill('d')).toBe('var(--text-muted)')
    expect(pt('d').querySelector('circle:last-child')!.getAttribute('fill-opacity')).toBe('0.4')
  })

  it('draws a team dot through the matchup slots, over its tone', () => {
    const dot = { '--team-home-light': '#111111' } as CSSProperties
    setup({ points: [{ key: 'a', label: 'A', x: 1, y: 1, tone: 'strong', dot }, { key: 'b', label: 'B', x: 2, y: 2 }] })
    const mark = pt('a').querySelector('[data-matchup] circle')!
    expect(mark.getAttribute('fill')).toBe('var(--team-home)')
    expect(mark.getAttribute('stroke')).toBe('var(--team-away)')
    expect(pt('b').querySelector('[data-matchup]')).toBeNull()
  })

  it('never draws two labels on top of each other', () => {
    setup()
    const labels = screen.getAllByTestId('label').map((t) => ({ x: Number(t.getAttribute('x')), y: Number(t.getAttribute('y')), w: t.textContent!.length * 7 }))
    for (let i = 0; i < labels.length; i++)
      for (let j = i + 1; j < labels.length; j++) {
        const a = labels[i]
        const b = labels[j]
        expect(a.x < b.x + b.w && b.x < a.x + a.w && Math.abs(a.y - b.y) < 12).toBe(false)
      }
  })

  it('labels every highlighted point, however crowded the plot', () => {
    const crowd = Array.from({ length: 30 }, (_, i) => ({ key: `T${i}`, label: `T${i}`, x: 0.5 + (i % 3) * 0.001, y: 0.5 + (i % 2) * 0.001, tone: 'muted' as const }))
    const strong = ['AA', 'BB', 'CC', 'DD'].map((k, i) => ({ key: k, label: k, x: 0.5 + i * 0.001, y: 0.5, tone: 'strong' as const }))
    const { container } = render(<Scatter label="Crowd" points={[...crowd, ...strong]} x={{ title: 'X', format: String }} y={{ title: 'Y', format: String }} />)
    const texts = [...container.querySelectorAll('text')].map((t) => t.textContent)
    for (const k of ['AA', 'BB', 'CC', 'DD']) expect(texts).toContain(k)
  })
})
