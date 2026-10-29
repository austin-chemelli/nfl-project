/** Pure helpers for the Method page. */
import type { Audit } from '../../data/contract'
import { ago, dash } from '../../lib/format'

/** '20261027T224658Z' -> Date (UTC), or null when it isn't a snapshot stamp. */
export function parseSnapshot(s: string | null | undefined): Date | null {
  const m = s?.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/)
  if (!m) return null
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]))
}

/** '2026-10-27 22:46 UTC' */
export function snapshotLabel(s: string | null | undefined): string {
  const d = parseSnapshot(s)
  return d ? `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC` : (s ?? dash)
}

export function snapshotAgo(s: string | null | undefined, now: Date = new Date()): string {
  const d = parseSnapshot(s)
  return d ? ago(d.toISOString(), now) : dash
}

export type NullRow = NonNullable<Audit['null_rates']>[number]

/** Columns with any missing values, highest null rate first (ties: most rows first). */
export function topNullRates(rows: NullRow[] | undefined, limit = 25): { shown: NullRow[]; total: number } {
  const withNulls = (rows ?? []).filter((r) => r.null_rate > 0)
  const sorted = [...withNulls].sort((a, b) => b.null_rate - a.null_rate || b.n_rows - a.n_rows)
  return { shown: sorted.slice(0, limit), total: withNulls.length }
}

/** Budget shares sorted largest first, dropping groups under half a point. */
export function sortedShares(share: Record<string, number>, min = 0.5): [string, number][] {
  return Object.entries(share).filter(([, v]) => v >= min).sort((a, b) => b[1] - a[1])
}
