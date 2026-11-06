/**
 * Label placement for the scatter. Pure and deterministic: no DOM measurement, so a label is
 * estimated at `7 * length + 4` px wide and 12 px tall, which keeps jsdom and the browser in step.
 * Points are visited outliers first (distance from the means), each tries eight positions around
 * its dot and keeps the first that clears placed labels, every dot and the obstacles. A point with
 * no clear position gets no label (the dot stays; hover and the table name it). Forced keys go
 * first, are always placed, and fall back to a less clean spot rather than vanish.
 */

export type LabelPoint = { key: string; text: string; x: number; y: number }
export type Rect = { x: number; y: number; w: number; h: number }
export type PlacedLabel = Rect & { key: string; text: string }
export type PlaceOptions = {
  /** Boxes to stay clear of, such as quadrant captions. */
  obstacles?: Rect[]
  /** Keys that must be labelled, placed before everyone else. */
  forced?: Iterable<string>
  /** Where the means sit in pixels; defaults to the centroid of the points. */
  center?: { x: number; y: number }
  /** Dot radius, default 5. */
  radius?: number
}

export const LABEL_H = 12

export const labelWidth = (text: string) => 7 * text.length + 4

const EPS = 0.01
export const overlaps = (a: Rect, b: Rect) =>
  a.x < b.x + b.w - EPS && b.x < a.x + a.w - EPS && a.y < b.y + b.h - EPS && b.y < a.y + a.h - EPS

const inside = (r: Rect, box: { width: number; height: number }) => r.x >= 0 && r.y >= 0 && r.x + r.w <= box.width && r.y + r.h <= box.height

/** The eight spots around a dot, in preference order: right, left, above, below, then the corners. */
function candidates(p: LabelPoint, w: number, r: number): Rect[] {
  const g = 2
  const h = LABEL_H
  const near = r + g
  return [
    { x: p.x + near, y: p.y - h / 2, w, h },
    { x: p.x - near - w, y: p.y - h / 2, w, h },
    { x: p.x - w / 2, y: p.y - near - h, w, h },
    { x: p.x - w / 2, y: p.y + near, w, h },
    { x: p.x + near, y: p.y - near - h + 3, w, h },
    { x: p.x - near - w, y: p.y - near - h + 3, w, h },
    { x: p.x + near, y: p.y + near - 3, w, h },
    { x: p.x - near - w, y: p.y + near - 3, w, h },
  ].map((c) => ({ ...c, w, h }))
}

export function placeLabels(points: LabelPoint[], box: { width: number; height: number }, options: PlaceOptions = {}): PlacedLabel[] {
  const { obstacles = [], radius = 5 } = options
  const forced = new Set(options.forced ?? [])
  const n = points.length
  const cx = options.center?.x ?? (n ? points.reduce((s, p) => s + p.x, 0) / n : 0)
  const cy = options.center?.y ?? (n ? points.reduce((s, p) => s + p.y, 0) / n : 0)
  const dist = (p: LabelPoint) => Math.hypot(p.x - cx, p.y - cy)
  const dots: Rect[] = points.map((p) => ({ x: p.x - radius, y: p.y - radius, w: 2 * radius, h: 2 * radius }))
  const order = points
    .map((p, i) => ({ p, i, forced: forced.has(p.key), d: dist(p) }))
    .sort((a, b) => Number(b.forced) - Number(a.forced) || b.d - a.d || a.i - b.i)

  const placed: PlacedLabel[] = []
  for (const { p, forced: must } of order) {
    const spots = candidates(p, labelWidth(p.text), radius)
    const clear = (c: Rect, withDots: boolean) =>
      inside(c, box) && !obstacles.some((o) => overlaps(c, o)) && !placed.some((l) => overlaps(c, l)) && (!withDots || !dots.some((d) => overlaps(c, d)))
    let pick = spots.find((c) => clear(c, true))
    if (!pick && must) pick = spots.find((c) => clear(c, false)) ?? spots.find((c) => inside(c, box) && !placed.some((l) => overlaps(c, l))) ?? spots[0]
    if (pick) placed.push({ ...pick, key: p.key, text: p.text })
  }
  // back to input order so callers and tests see a stable list
  const at = new Map(points.map((p, i) => [p.key, i]))
  return placed.sort((a, b) => (at.get(a.key) ?? 0) - (at.get(b.key) ?? 0))
}
