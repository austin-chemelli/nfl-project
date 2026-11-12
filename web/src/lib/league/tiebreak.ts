/**
 * NFL standings tiebreakers: a copy of src/nfl/league/tiebreak.py (M26.3). Division ranks and
 * playoff seeds by the real procedure through the points steps, then a coin flip from `rng`.
 * Only one club advances per step; clubs eliminated at a step send the rest back to step 1.
 */
import { CONFERENCE_SET, DIVISION_SET, DIVISION_TEAMS, DIVISIONS, type Conf } from './divisions'
import { Results, without } from './standings'

/** A uniform number in [0, 1); used only by the final coin flip. */
export type Rng = () => number
export type Trace = [string, string, number][]

type Vals = Map<string, number | null>
type Measure = (r: Results, ts: string[]) => Vals
type Step = [string, Measure, boolean]

const each = (ts: string[], f: (t: string) => number | null): Vals => new Map(ts.map((t) => [t, f(t)]))

const h2h: Measure = (r, ts) => each(ts, (t) => r.pctVs(t, without(ts, [t])))
const h2hWc: Measure = (r, ts) => {
  const [a, b] = ts
  return r.gamesVs(a, [b]) === 0 ? each(ts, () => 0) : h2h(r, ts)
}
const h2hSweep: Measure = (r, ts) =>
  each(ts, (t) => {
    const others = ts.filter((o) => o !== t)
    if (!others.every((o) => r.gamesVs(t, [o]) > 0)) return 0
    const [w, l, tie] = r.recordVs(t, others)
    return l === 0 && tie === 0 ? 1 : w === 0 && tie === 0 ? -1 : 0
  })
const divisionRec: Measure = (r, ts) => each(ts, (t) => r.pctVs(t, without(DIVISION_SET[t], [t])))
const conferenceRec: Measure = (r, ts) => each(ts, (t) => r.pctVs(t, without(CONFERENCE_SET[DIVISIONS[t][0]], [t])))
const common: Measure = (r, ts) => {
  const c = r.commonOpponents(ts)
  return each(ts, (t) => r.pctVs(t, c))
}
const common4: Measure = (r, ts) => {
  const c = r.commonOpponents(ts)
  if (ts.some((t) => r.gamesVs(t, c) < 4)) return each(ts, () => 0)
  return each(ts, (t) => r.pctVs(t, c))
}
const sov: Measure = (r, ts) => each(ts, (t) => r.sov(t))
const sos: Measure = (r, ts) => each(ts, (t) => r.sos(t))
const confPoints: Measure = (r, ts) => each(ts, (t) => -(r.pointsRanks()[1].get(t) ?? 0))
const leaguePoints: Measure = (r, ts) => each(ts, (t) => -(r.pointsRanks()[0].get(t) ?? 0))
const netCommon: Measure = (r, ts) => {
  const c = r.commonOpponents(ts)
  return each(ts, (t) => r.netPoints(t, c))
}
const netConf: Measure = (r, ts) => each(ts, (t) => r.netPoints(t, without(CONFERENCE_SET[DIVISIONS[t][0]], [t])))
const netAll: Measure = (r, ts) => each(ts, (t) => r.netPoints(t))

const DIVISION_STEPS: Step[] = [
  ['h2h', h2h, false],
  ['division', divisionRec, false],
  ['common', common, false],
  ['conference', conferenceRec, false],
  ['sov', sov, false],
  ['sos', sos, false],
  ['conf_points', confPoints, true],
  ['league_points', leaguePoints, true],
  ['net_common', netCommon, true],
  ['net_all', netAll, true],
]
const WILDCARD_STEPS_2: Step[] = [
  ['h2h', h2hWc, false],
  ['conference', conferenceRec, false],
  ['common4', common4, false],
  ['sov', sov, false],
  ['sos', sos, false],
  ['conf_points', confPoints, true],
  ['league_points', leaguePoints, true],
  ['net_conf', netConf, true],
  ['net_all', netAll, true],
]
const WILDCARD_STEPS_N: Step[] = [['h2h_sweep', h2hSweep, false], ...WILDCARD_STEPS_2.slice(1)]

const sorted = (xs: Iterable<string>) => [...xs].sort()

/** Clubs holding the best value; a null (not applicable) means the step eliminates nobody. */
function winners(vals: Vals): string[] {
  const vs = [...vals.values()]
  if (vs.some((v) => v === null)) return [...vals.keys()]
  const m = Math.max(...(vs as number[]))
  return [...vals.entries()].filter(([, v]) => v === m).map(([t]) => t)
}

function coin(ts: string[], rng: Rng, ctx: string, trace?: Trace): string {
  trace?.push([ctx, 'coin', ts.length])
  return sorted(ts)[Math.floor(rng() * ts.length)]
}

function run(r: Results, ts: string[], steps: Step[], ctx: string, redo: (s: string[]) => string, rng: Rng, trace?: Trace): string {
  for (const [name, fn, needsScores] of steps) {
    if (needsScores && !r.scored) continue
    const win = winners(fn(r, ts))
    if (win.length === 1) {
      trace?.push([ctx, name, ts.length])
      return win[0]
    }
    if (win.length < ts.length) return redo(sorted(win))
  }
  return coin(ts, rng, ctx, trace)
}

export function breakDivisionTie(r: Results, tied: string[], rng: Rng, trace?: Trace): string {
  const ts = sorted(tied)
  if (ts.length === 1) return ts[0]
  return run(r, ts, DIVISION_STEPS, 'division', (s) => breakDivisionTie(r, s, rng, trace), rng, trace)
}

/** A tie for a wild-card spot or among division winners; `divorder` keeps each division's best club in a tie of three or more. */
export function breakWildcardTie(r: Results, tied: string[], divorder: Record<string, string[]>, rng: Rng, trace?: Trace): string {
  const ts = sorted(tied)
  if (ts.length === 1) return ts[0]
  const divs = new Set(ts.map((t) => DIVISIONS[t][1]))
  if (divs.size === 1) return breakDivisionTie(r, ts, rng, trace)
  if (ts.length > 2) {
    const keep = sorted(
      [...divs].map((d) => ts.filter((t) => DIVISIONS[t][1] === d).reduce((a, b) => (divorder[d].indexOf(b) < divorder[d].indexOf(a) ? b : a))),
    )
    if (keep.length < ts.length) return breakWildcardTie(r, keep, divorder, rng, trace)
  }
  const steps = ts.length === 2 ? WILDCARD_STEPS_2 : WILDCARD_STEPS_N
  return run(r, ts, steps, 'wildcard', (s) => breakWildcardTie(r, s, divorder, rng, trace), rng, trace)
}

/** The best `n` clubs of `pool` by win percentage, ties broken one winner at a time. */
function order(r: Results, pool: string[], n: number, pick: (tied: string[]) => string): string[] {
  const left = [...pool]
  const out: string[] = []
  while (left.length && out.length < n) {
    const m = Math.max(...left.map((t) => r.pct(t)))
    const tied = left.filter((t) => r.pct(t) === m)
    const w = tied.length > 1 ? pick(tied) : tied[0]
    out.push(w)
    left.splice(left.indexOf(w), 1)
  }
  return out
}

/** The four clubs of `division`, first place to last. */
export function rankDivision(r: Results, division: string, rng: Rng, trace?: Trace): string[] {
  return order(r, [...DIVISION_TEAMS[division]], 4, (tied) => breakDivisionTie(r, tied, rng, trace))
}

/** The `nSeeds` playoff clubs of `conf` in seed order: four division winners, then wild cards (7 from 2020, 6 before). */
export function seedConference(r: Results, conf: Conf, rng: Rng, nSeeds = 7, trace?: Trace): string[] {
  const divorder: Record<string, string[]> = {}
  for (const d of Object.keys(DIVISION_TEAMS)) if (d.startsWith(conf)) divorder[d] = rankDivision(r, d, rng, trace)
  const pick = (tied: string[]) => breakWildcardTie(r, tied, divorder, rng, trace)
  const orders = Object.values(divorder)
  const seeds = order(r, orders.map((o) => o[0]), 4, pick)
  const rest = orders.flatMap((o) => o.slice(1))
  return [...seeds, ...order(r, rest, nSeeds - 4, pick)]
}
