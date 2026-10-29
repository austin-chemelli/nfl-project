/**
 * Season view maths (src/nfl/ui/pages/season.py): one weight set against every game of a season.
 * Probabilities come from `seasonPredictions` on the matrix (walk-forward Platt); the biggest push
 * per game uses the season file's composites.
 */
import { EPS, prepare, seasonPredictions, seasonWeights, type MatrixInput } from './evaluate'
import type { Weights } from './weights'

export interface SeasonDoc {
  season: number
  groups: string[]
  game_id: string[]
  week: number[]
  home: string[]
  away: string[]
  kickoff: (string | null)[]
  result: (number | null)[]
  home_won: number[]
  market_p: (number | null)[]
  c: Record<string, readonly number[]>
}

export interface SeasonGame {
  game_id: string
  week: number
  home: string
  away: string
  kickoff: string | null
  result: number | null
  home_won: number
  p: number
  market_p: number | null
  correct: boolean
  market_correct: boolean | null
  ll: number
  market_ll: number | null
  /** group with the largest push, null when no push reaches 0.05 pts */
  push_group: string | null
  /** win-probability points the group moved p toward the home team (negative = toward the road team) */
  push_pts: number
}

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))
const clip = (p: number) => Math.min(Math.max(p, EPS), 1 - EPS)
const loss = (p: number, y: number) => -(y * Math.log(clip(p)) + (1 - y) * Math.log(1 - clip(p)))

/** One row per game: probabilities, result, pick correctness, and the biggest group push. */
export function seasonGames(doc: SeasonDoc, matrix: MatrixInput, weights: Weights): SeasonGame[] {
  const sp = seasonPredictions(weights, matrix, doc.season)
  const byId = new Map(sp.game_id.map((id, i) => [id, sp.p[i]]))
  const groups = doc.groups
  const W = seasonWeights(weights, doc.season, groups)
  return doc.game_id.map((id, i) => {
    const p = byId.get(id) ?? NaN
    const logit = Math.log(clip(p) / clip(1 - p))
    let push = 0
    let top = -1
    let best = ''
    groups.forEach((g, j) => {
      const contrib = sp.calib_a * W[j] * doc.c[g][i]
      const pts = 100 * (p - sigmoid(logit - contrib))
      if (Math.abs(pts) > top) { top = Math.abs(pts); push = pts; best = g }
    })
    const y = doc.home_won[i]
    const mk = doc.market_p[i]
    return {
      game_id: id, week: doc.week[i], home: doc.home[i], away: doc.away[i], kickoff: doc.kickoff[i],
      result: doc.result[i], home_won: y, p, market_p: mk,
      correct: (p >= 0.5) === (y === 1),
      market_correct: mk == null ? null : (mk >= 0.5) === (y === 1),
      ll: loss(p, y), market_ll: mk == null ? null : loss(mk, y),
      push_group: Math.abs(push) < 0.05 ? null : best, push_pts: push,
    }
  })
}

export interface WeekEdge {
  week: number
  games: number
  /** mean of (market log loss − yours): positive = closer to what happened than the market */
  edge: number
  right: number
}

/** Per week: games priced by the market, edge over the market per game, picks right. */
export function weekTable(games: SeasonGame[]): WeekEdge[] {
  const by = new Map<number, { n: number; e: number; right: number }>()
  for (const g of games) {
    if (g.market_ll == null) continue
    const w = by.get(g.week) ?? { n: 0, e: 0, right: 0 }
    w.n++
    w.e += g.market_ll - g.ll
    w.right += g.correct ? 1 : 0
    by.set(g.week, w)
  }
  return [...by.entries()].sort((a, b) => a[0] - b[0]).map(([week, w]) => ({ week, games: w.n, edge: w.e / w.n, right: w.right }))
}

export interface SeasonSummary {
  n: number
  log_loss: number
  market_log_loss: number | null
  right: number
  market_right: number
  market_n: number
}

export function summarize(games: SeasonGame[]): SeasonSummary | null {
  if (!games.length) return null
  const priced = games.filter((g) => g.market_ll != null)
  const mean = (a: number[]) => a.reduce((x, v) => x + v, 0) / a.length
  return {
    n: games.length,
    log_loss: mean(games.map((g) => g.ll)),
    market_log_loss: priced.length ? mean(priced.map((g) => g.market_ll as number)) : null,
    right: games.filter((g) => g.correct).length,
    market_right: priced.filter((g) => g.market_correct).length,
    market_n: priced.length,
  }
}

/** Last scored season of the matrix. */
export function lastSeason(matrix: MatrixInput): number {
  const P = prepare(matrix)
  let m = 0
  for (let i = 0; i < P.n; i++) if (!P.warmup[i] && P.season[i] > m) m = P.season[i]
  return m
}
