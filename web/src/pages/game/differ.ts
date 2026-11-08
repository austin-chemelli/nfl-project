/** Words for where an approach differs from the market, and for the quarterback what-if (ADR 0024). */
import type { Game, StrongCall, Swing } from '../../data/contract'
import { pct } from '../../lib/format'
import { APPROACHES, HEADLINE, SHORT } from '../../lib/models'

/** "Lamar Jackson questionable" / "Lamar Jackson" when he's not on the report. */
export function whoText(s: { name: string | null; status: string | null } | null): string {
  if (!s?.name) return 'the listed starter'
  return s.status ? `${s.name} (${s.status.toLowerCase()})` : s.name
}

/** Why the what-if exists, in a few words. */
export const WHY: Record<string, string> = {
  status: 'the starter is on the injury report',
  chart: 'the depth chart lists someone else first',
  usual: 'the usual starter is listed as questionable',
}

/** "If Tyler Huntley starts: the Student has BAL 54% (62% as locked)." from the home team's view of the side. */
export function whatIfLine(g: Game, s: Swing, model: string = HEADLINE): string | null {
  const a = s.assumed?.p_home[model]
  const b = s.alternative?.p_home[model]
  if (a == null || b == null || !s.alternative?.name) return null
  const team = s.team ?? g.home
  const side = (p: number) => (team === g.home ? p : 1 - p)
  return `If ${s.alternative.name} starts: the ${SHORT[model] ?? model} has ${team} at ${pct(side(b))}, against ${pct(side(a))} with ${s.assumed?.name ?? 'the assumed starter'}.`
}

/** "Right · the line moved toward it" for a graded call; null before the game. */
export function outcome(c: StrongCall): string | null {
  if (c.result == null) return null
  const r = c.result === 'tie' ? 'Tie' : c.result === 'right' ? 'Right' : 'Wrong'
  const m = c.closing_toward == null ? '' : c.closing_toward ? ' · the line moved toward it' : ' · the line moved away from it'
  return r + m
}

/** The other swing factors, as plain lines. */
export function factorLines(swings: Swing[]): string[] {
  return swings.filter((s) => s.kind !== 'qb' && s.text).map((s) => s.text!)
}

/** An approach 10+ points of win chance from the market (the strong-call bar, ADR 0024). */
export const STRONG_GAP = 0.1

export type Gap = { model: string; team: string; p: number; market: number; gap: number; groups: string[]; locked: boolean }

/** Every approach's gap to the market on this game right now, largest first, with the groups pulling
 * its way (from the same contributions the "why" chart draws). An approach whose call the lock
 * already recorded is left out: its recorded sentence is shown instead. */
export function liveGaps(g: Game, groupName: (id: string) => string): Gap[] {
  const mk = g.market?.p_home ?? g.models.market_baseline?.p_home ?? null
  if (mk == null) return []
  const recorded = new Set(g.strong_calls.map((c) => c.model_id))
  const out: Gap[] = []
  for (const m of APPROACHES) {
    const p = g.models[m]?.p_home
    if (p == null || recorded.has(m)) continue
    const gap = p - mk
    const home = gap >= 0
    const toward = Object.entries(g.contributions[m]?.groups ?? {})
      .map(([id, x]) => ({ id, pp: x.pp ?? 0 }))
      .filter((x) => (home ? x.pp > 0.5 : x.pp < -0.5))
      .sort((a, b) => Math.abs(b.pp) - Math.abs(a.pp))
      .slice(0, 3)
      .map((x) => groupName(x.id))
    out.push({ model: m, team: home ? g.home : g.away, p: home ? p : 1 - p, market: home ? mk : 1 - mk, gap: Math.abs(gap), groups: toward, locked: g.models[m]?.status === 'locked' })
  }
  return out.sort((a, b) => b.gap - a.gap)
}

const joinNames = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`)

/** "has CIN at 70% against the market's 59%, leaning on Quarterback, Offense and Form." */
export function gapSentence(x: Gap): string {
  const lean = x.groups.length ? `, leaning on ${joinNames(x.groups)}` : ''
  return `has ${x.team} at ${pct(x.p)} against the market's ${pct(x.market)}${lean}.`
}
