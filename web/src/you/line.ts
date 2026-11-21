/**
 * A custom line's maths (ADR 0034), shared by every page that shows "You":
 *
 *   p_home = σ(a · Σ_g W_g c_g + c · g)        g = 1 at a home game, 0 at a neutral site
 *
 * W: the reader's points, normalized (sum of |W| = 1, Market behavior at most 20%: `normalize`).
 * c_g: the engine's group composites for the game, as of the lock (site data `composites`).
 * (a, c): Platt calibration fitted on every season of the Build matrix before the scored season,
 * with the same neutral-site gate as the engine. Published lines follow the same formula with their
 * own W, intercept and calibration, which the parity test checks.
 */
import type { Composites, Contribution } from '../data/contract'
import { normalize, platt, prepare, rawLogit, type GroupWeights, type MatrixInput } from '../diy'

export const SD_MARGIN = 13.5
const P_CLIP = 1e-6

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))

/** Φ⁻¹(p) (Acklam's rational approximation, |error| < 1.2e-9; scipy's norm.ppf in the engine). */
export function probit(p: number): number {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239]
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572]
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416]
  const lo = 0.02425
  if (p <= 0) return -Infinity
  if (p >= 1) return Infinity
  if (p < lo) {
    const q = Math.sqrt(-2 * Math.log(p))
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  if (p > 1 - lo) {
    const q = Math.sqrt(-2 * Math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  const q = p - 0.5
  const r = q * q
  return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
}

/** A line in the engine's linear form: logit = a·(b·g + Σ W c) + c·g. A custom line has b = 0. */
export interface LineParams {
  W: GroupWeights
  intercept: number
  a: number
  c: number
}

export interface Scored {
  p_home: number
  spread_home: number
  logit: number
  /** logit pieces: home field (a·b·g + c·g) and a·W_g·c_g per group; they sum to `logit` */
  home_field: number
  groups: GroupWeights
}

/** Score one game's composites with a line (`engine.Model.score`, at the group level). */
export function scoreLine(line: LineParams, comp: Pick<Composites, 'neutral' | 'c'>): Scored {
  const g = comp.neutral ? 0 : 1
  const groups: GroupWeights = {}
  let x = 0
  for (const [id, w] of Object.entries(line.W)) {
    const v = comp.c[id]
    if (v == null || !w) continue
    groups[id] = line.a * w * v
    x += w * v
  }
  const home = line.a * line.intercept * g + line.c * g
  const logit = line.a * x + home
  const p = Math.min(Math.max(sigmoid(logit), P_CLIP), 1 - P_CLIP)
  return { p_home: p, spread_home: probit(p) * SD_MARGIN, logit, home_field: home, groups }
}

/** Points of home win chance a piece is worth: p(with it) − p(without it), ×100 (site.py `_pp`). */
const pp = (total: number, piece: number) => Math.round(1000 * (sigmoid(total) - sigmoid(total - piece))) / 10

/** The Preview's breakdown for a scored custom line, in the shape the site publishes per model. */
export function contributionOf(s: Scored): Contribution {
  const groups: Contribution['groups'] = {}
  for (const [id, v] of Object.entries(s.groups)) groups[id] = { pp: pp(s.logit, v), features: {} }
  return { p_home: Math.round(1e4 * sigmoid(s.logit)) / 1e4, home_field_pp: pp(s.logit, s.home_field), groups }
}

/**
 * The calibration for a custom line scored in season `season`: Platt with the neutral-site gate on
 * every matrix row of an earlier season (warmup rows included), as Build's walk-forward does.
 */
export function calibrate(weights: GroupWeights, matrix: MatrixInput, season: number): { a: number; c: number } {
  const P = prepare(matrix)
  const raw = rawLogit(P, weights)
  const x: number[] = []
  const y: number[] = []
  const g: number[] = []
  for (let i = 0; i < P.n; i++) {
    if (P.season[i] >= season) continue
    x.push(raw[i])
    y.push(P.y[i])
    g.push(P.g[i])
  }
  const [a, c] = platt(x, y, g)
  return { a, c }
}

/**
 * Live-only groups (Market behavior, Buzz) are zero in every past season, so the calibration's slope
 * is fitted on the groups with history alone and then applied to the whole lean. If the live-only
 * groups held most of the budget, that slope would blow them up (a lean that is 95% Buzz gets a slope
 * twenty times too steep). So together they hold at most this share of a custom line's budget, about
 * what the personas give them (the Sharp: 20%).
 */
export const LIVE_CAP = 0.3
export const LIVE_ONLY = ['market', 'buzz']

/** Scale the live-only groups down so they hold at most LIVE_CAP of the budget. Returns the points and whether it did. */
export function capLive(points: GroupWeights, live: readonly string[] = LIVE_ONLY): [GroupWeights, boolean] {
  let l = 0
  let rest = 0
  for (const [g, v] of Object.entries(points)) {
    if (live.includes(g)) l += Math.abs(v)
    else rest += Math.abs(v)
  }
  const limit = (LIVE_CAP / (1 - LIVE_CAP)) * rest
  if (l <= limit + 1e-12) return [{ ...points }, false]
  const k = l > 0 ? limit / l : 0
  return [Object.fromEntries(Object.entries(points).map(([g, v]) => [g, live.includes(g) ? v * k : v])), true]
}

/** The weights a custom line uses: live-only groups capped, Market behavior capped, normalized. */
export const youWeights = (points: GroupWeights, live: readonly string[] = LIVE_ONLY): GroupWeights =>
  normalize(capLive(points, live)[0]).weights

/** Points -> the custom line for a season (its weights, b = 0, the calibration given). */
export const customLine = (points: GroupWeights, calib: { a: number; c: number }, live: readonly string[] = LIVE_ONLY): LineParams => ({
  W: youWeights(points, live), intercept: 0, a: calib.a, c: calib.c,
})
