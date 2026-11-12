/** Small helpers for the Matchups tab and the upset card (ranks and league quartiles). */
import type { MatchupRow } from '../data/contract'

/** 1 -> 1st, 22 -> 22nd, 13 -> 13th. */
export const ordinal = (n: number) => {
  const r = n % 100
  const s = r >= 11 && r <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${s}`
}

/** 1-4: the quartile of the league's teams the habit falls in. */
export function quartile(r: Pick<MatchupRow, 'opp_rate' | 'opp_rate_q1' | 'opp_rate_med' | 'opp_rate_q3'>): number | null {
  const { opp_rate: v, opp_rate_q1: a, opp_rate_med: m, opp_rate_q3: b } = r
  if (v == null || a == null || m == null || b == null) return null
  return v < a ? 1 : v < m ? 2 : v < b ? 3 : 4
}
