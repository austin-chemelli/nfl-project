/** Words for where an approach differs from the market, and for the quarterback what-if (ADR 0023). */
import type { Game, StrongCall, Swing } from '../../data/contract'
import { pct } from '../../lib/format'
import { HEADLINE, SHORT } from '../../lib/models'

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
