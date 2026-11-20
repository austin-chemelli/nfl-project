/** Plain helpers shared by the betting pages (no components). */
import type { MathBand } from '../../data/contract'
import { dash, pct } from '../../lib/format'

export const tip = { background: 'var(--surface-1)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13 }
export const axis = { stroke: 'var(--text-muted)', tick: { fontSize: 12 } }

/** A chance with no false precision: "72%", "<1%" for a sliver, "0%" for none. */
export function chance(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return dash
  if (p === 0) return '0%'
  if (p < 0.01) return '<1%'
  return pct(p, 0)
}

/** Prices in the file are printed with a hyphen ("-400 or shorter"); show a real minus. */
export const minus = (s: string) => s.replace(/(^|[\s(])-(\d)/g, '$1−$2')

/** The calendar periods a band carries a return for (`roi_2006-2015`, `roi_2016-2025`, a lone `roi_2026`), oldest first. */
export function periodKeys(b: MathBand | undefined): string[] {
  if (!b) return []
  return Object.keys(b)
    .map((k) => /^roi_(\d{4}(?:-\d{4})?)$/.exec(k)?.[1])
    .filter((p): p is string => p != null)
    .sort()
}

export const periodLabel = (p: string) => p.replace('-', '–')

/** A numeric field of a loose object, or null. */
export function field(o: object | undefined, key: string): number | null {
  const v = (o as Record<string, unknown> | undefined)?.[key]
  return typeof v === 'number' ? v : null
}
