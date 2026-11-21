import type { NewsEffect } from '../../data/contract'

const g = (n: number) => `${n} game${n === 1 ? '' : 's'}`

/** Plain-words summary of the news effect: no log-odds, and no verdict from a handful of games. */
export function newsEffectText(e: NewsEffect): { lede: string; verdict: string } {
  const lede =
    e.moved === 0
      ? `In ${g(e.games)} so far, the news hasn't moved the Student's line.`
      : `The news moved the Student's line in ${e.moved} of ${g(e.games)}, by ${e.mean_abs_pts?.toFixed(1) ?? '–'} points on average.`
  if (e.moved === 0 || e.delta_log_loss == null) return { lede, verdict: 'Nothing to judge yet.' }
  const d = e.delta_log_loss
  const side = d < 0 ? 'better' : 'worse'
  const clear = e.lo != null && e.hi != null && (e.lo > 0 || e.hi < 0)
  const verdict = clear
    ? `Against the football-only twin it scored ${Math.abs(d).toFixed(3)} log loss ${side}, a gap the range (${e.lo?.toFixed(3)} to ${e.hi?.toFixed(3)}) doesn't cross zero on.`
    : `Against the football-only twin the gap is ${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(3)} log loss, inside the noise at ${g(e.games)}: too early to tell.`
  return { lede, verdict }
}
