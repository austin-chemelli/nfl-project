/** Human-readable formatting (contract v2: nothing in log-odds reaches the page). */

export const dash = '–'

export function pct(p: number | null | undefined, digits = 0): string {
  return p == null || Number.isNaN(p) ? dash : `${(100 * p).toFixed(digits)}%`
}

/** Win-probability points with a sign: "+3.9 pts". */
export function pts(x: number | null | undefined, digits = 1): string {
  return x == null ? dash : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(digits)} pts`
}

/** "+3.9 pts toward GB" for a contribution in win-probability points (positive = home). */
export function ptsToward(x: number | null | undefined, home: string, away: string): string {
  if (x == null) return dash
  if (Math.abs(x) < 0.05) return '0.0 pts'
  return `${pts(x)} toward ${x > 0 ? home : away}`
}

/** Book-style line from the home spread (+ = home favored): "BUF −3.5". */
export function spreadLabel(s: number | null | undefined, home: string, away: string): string {
  if (s == null) return dash
  if (Math.abs(s) < 0.25) return "pick'em"
  return `${s > 0 ? home : away} −${Math.abs(s)}`
}

/** The favored team and its win probability: "BUF 64%". */
export function pick(pHome: number | null | undefined, home: string, away: string): string {
  if (pHome == null) return dash
  return pHome >= 0.5 ? `${home} ${pct(pHome)}` : `${away} ${pct(1 - pHome)}`
}

const ET = 'America/New_York'
export function kickoffEt(ts: string | null | undefined): string {
  if (!ts) return dash
  const d = new Date(ts)
  return d.toLocaleString('en-US', { timeZone: ET, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) + ' ET'
}

export function ago(ts: string | null | undefined, now: Date = new Date()): string {
  if (!ts) return dash
  const s = Math.max(0, (now.getTime() - new Date(ts).getTime()) / 1000)
  if (s < 90) return 'just now'
  if (s < 5400) return `${Math.round(s / 60)} min ago`
  if (s < 129600) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} days ago`
}

/** Format a raw feature value by its registry unit (mirrors nfl.ui.data.fmt). */
export function fmtUnit(value: number | null | undefined, unit: string | null | undefined): string {
  if (value == null || Number.isNaN(value)) return dash
  const v = value
  const sign = (x: number, d: number) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(d)}`
  switch (unit) {
    case 'pct': return `${(100 * v).toFixed(0)}%`
    case 'pp': return `${sign(v, 1)} pts`
    case 'prob_diff': return `${sign(100 * v, 1)} pts`
    case 'points': return sign(v, 1)
    case 'rating': return v.toFixed(0)
    case 'epa': return sign(v, 3)
    case 'days': case 'count': case 'seasons': return Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1)
    case 'km': return `${Math.round(v).toLocaleString('en-US')} km`
    case 'hours': return `${sign(v, 0)} h`
    case 'seconds': return `${v.toFixed(2)} s`
    case 'yards': return `${v.toFixed(0)} yds`
    case 'flag': return v >= 0.5 ? 'yes' : 'no'
    default: return v.toFixed(2)
  }
}

/** Log loss with context, never alone: "0.630 (0.021 worse than the market)". */
export function llVsMarket(ll: number, market: number): string {
  const d = ll - market
  if (Math.abs(d) < 0.0005) return `${ll.toFixed(3)} (same as the market)`
  return `${ll.toFixed(3)} (${Math.abs(d).toFixed(3)} ${d > 0 ? 'worse' : 'better'} than the market)`
}
