import { describe, expect, it } from 'vitest'
import { labelWidth, LABEL_H, overlaps, placeLabels, type LabelPoint } from './labels'

const BOX = { width: 300, height: 260 }

/** Small deterministic generator, so a seed always gives the same cloud. */
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

const KEYS = Array.from({ length: 32 }, (_, i) => `T${String.fromCharCode(65 + (i % 26))}${i}`)

function cloud(seed: number): LabelPoint[] {
  const r = rng(seed)
  // clustered: four tight groups
  const centres = [[80, 70], [200, 90], [120, 190], [220, 200]]
  return KEYS.map((k, i) => {
    const [cx, cy] = centres[i % 4]
    return { key: k, text: k.slice(0, 3), x: cx + (r() - 0.5) * 40, y: cy + (r() - 0.5) * 30 }
  })
}

describe('placeLabels', () => {
  it('never returns two overlapping boxes, or one over a dot (32 clustered points, 50 seeds)', () => {
    for (let seed = 1; seed <= 50; seed++) {
      const pts = cloud(seed)
      const out = placeLabels(pts, BOX)
      for (let i = 0; i < out.length; i++) {
        for (let j = i + 1; j < out.length; j++) expect(overlaps(out[i], out[j])).toBe(false)
        for (const p of pts) expect(overlaps(out[i], { x: p.x - 5, y: p.y - 5, w: 10, h: 10 })).toBe(false)
      }
    }
  })

  it('always labels the forced key, even in a crowd', () => {
    for (let seed = 1; seed <= 50; seed++) {
      const pts = cloud(seed)
      const key = pts[seed % pts.length].key
      const out = placeLabels(pts, BOX, { forced: [key] })
      expect(out.some((l) => l.key === key)).toBe(true)
    }
  })

  it('is deterministic', () => {
    const pts = cloud(7)
    expect(placeLabels(pts, BOX, { forced: ['TC2'] })).toEqual(placeLabels(pts, BOX, { forced: ['TC2'] }))
  })

  it('sizes a label at 7 px a character plus 4, 12 px tall', () => {
    const [l] = placeLabels([{ key: 'a', text: 'KC', x: 100, y: 100 }], BOX)
    expect(l.w).toBe(labelWidth('KC'))
    expect(l.w).toBe(18)
    expect(l.h).toBe(LABEL_H)
  })

  it('puts a lone label to the right of its dot', () => {
    const [l] = placeLabels([{ key: 'a', text: 'KC', x: 100, y: 100 }], BOX)
    expect(l.x).toBeGreaterThan(100)
  })

  it('moves to another position when the first is blocked, and drops the label when none is clear', () => {
    const pts = [{ key: 'a', text: 'KC', x: 100, y: 100 }]
    const right = placeLabels(pts, BOX)[0]
    const moved = placeLabels(pts, BOX, { obstacles: [right] })[0]
    expect(overlaps(moved, right)).toBe(false)
    const wall = { x: 0, y: 0, w: BOX.width, h: BOX.height }
    expect(placeLabels(pts, BOX, { obstacles: [wall] })).toEqual([])
  })

  it('keeps labels clear of obstacles', () => {
    const obstacle = { x: 60, y: 50, w: 80, h: 40 }
    for (const l of placeLabels(cloud(3), BOX, { obstacles: [obstacle] })) expect(overlaps(l, obstacle)).toBe(false)
  })

  it('labels the outlier before a crowd member competing for the same spot', () => {
    const pts: LabelPoint[] = [
      { key: 'mid', text: 'AA', x: 150, y: 130 },
      { key: 'far', text: 'BB', x: 20, y: 20 },
    ]
    const out = placeLabels(pts, BOX, { center: { x: 150, y: 130 } })
    expect(out.map((l) => l.key)).toEqual(['mid', 'far'])
  })

  it('stays inside the box', () => {
    for (const l of placeLabels([{ key: 'a', text: 'KC', x: 295, y: 5 }], BOX)) {
      expect(l.x + l.w).toBeLessThanOrEqual(BOX.width)
      expect(l.y).toBeGreaterThanOrEqual(0)
    }
  })
})
