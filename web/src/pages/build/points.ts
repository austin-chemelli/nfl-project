/** Slider state helpers for the Build page: signed attention points per group. */
import type { Group } from '../../data/contract'
import type { GroupWeights } from '../../diy'

/** Equal weights on every active group ("Blank"). */
export const blankPoints = (active: string[]): GroupWeights => Object.fromEntries(active.map((g) => [g, 50]))

/** Heading -> share of the (capped, normalized) budget, in meta heading order. */
export function headingShares(weights: GroupWeights, groups: Group[], headings: string[]): { heading: string; share: number }[] {
  const by = new Map(headings.map((h) => [h, 0]))
  for (const g of groups) by.set(g.heading, (by.get(g.heading) ?? 0) + Math.abs(weights[g.id] ?? 0))
  return [...by.entries()].map(([heading, share]) => ({ heading, share: 100 * share }))
}

/** "2015 W3: GB @ CHI" from a game id like 2015_03_GB_CHI (away first, as in the id). */
export function gameLabel(id: string): string {
  const p = id.split('_')
  return p.length === 4 ? `${p[0]} W${Number(p[1])}: ${p[2]} @ ${p[3]}` : id
}

/** Signed share text: "+12%" / "−8%". */
export const signedPct = (x: number, digits = 0) => `${x < 0 ? '−' : '+'}${Math.abs(x).toFixed(digits)}%`

/** One step of a ramp from the accent to muted gray: headings have no palette of their own. */
export const rampColor = (i: number, n: number) => `color-mix(in srgb, var(--accent) ${Math.round(100 - (70 * i) / Math.max(1, n - 1))}%, var(--text-muted))`
