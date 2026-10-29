/**
 * The build-your-own evaluator, ported from nfl.approaches.diy (pure functions, no React).
 *
 * Scoring group weights W over the matrix of group composites c_g is a matrix multiply plus a
 * walk-forward Platt calibration: p = σ(a_S · Σ_g W_g c_g + c_S) with (a_S, c_S) fitted on earlier
 * seasons only (slope constrained to a ≥ 0). Result objects keep Python's snake_case keys so the
 * parity test can compare them one to one. Differences from Python: bootstrap intervals use a
 * different random stream (see rng.ts), and `accuracy`, `market_accuracy` and `reliability` are
 * extra fields the page shows.
 */
import { mulberry32, nanQuantile } from './rng'
import { isPerSeason, type GroupWeights, type Weights } from './weights'

export const BOOTSTRAP = 500
export const EPS = 1e-6
export const EDGE_THRESHOLD = 0.05
/** |model p − market p| bucket edges (nfl.grade.DIVERGENCE_BUCKETS). */
export const DIVERGENCE_BUCKETS = [0, 0.025, 0.05, 0.1]
export const LAST_SEASON_FALLBACK = 2025

const SPREAD_LABELS: [number, string][] = [[0, "Pick'em (under 3)"], [1, 'Moderate (3 to 7)'], [2, 'Big favorite (7+)']]
const MONTH_LABELS: [number, string][] = [[9, 'September'], [10, 'October'], [11, 'November'], [12, 'December'], [13, 'January+']]
const FAV_LABELS: [number, string][] = [[1, 'Home favorite'], [0, "Pick'em line"], [-1, 'Home underdog']]
const DIV_LABELS = ['0-2.5', '2.5-5', '5-10', '10+']

// ----------------------------------------------------------------------------------------- input

type Col = readonly unknown[]

/** The diy_matrix.json shape (structurally compatible with the zod `DiyMatrix` type). */
export interface MatrixInput {
  groups: string[]
  inactive?: string[]
  first_scored?: number
  columns: { [k: string]: unknown }
  c: Record<string, readonly number[]>
  personas?: Record<string, { name: string; intercept: number; W: GroupWeights }>
  student_fitted?: Record<string, { intercept: number; W: GroupWeights }>
}

export interface Prepared {
  n: number
  groups: string[]
  inactive: string[]
  /** (n × groups) composites, row-major */
  C: Float64Array
  season: Int32Array
  warmup: Uint8Array
  y: Float64Array
  mkt: Float64Array
  result: Float64Array
  home_ml: Float64Array
  away_ml: Float64Array
  week: Float64Array
  game_id: string[]
  first_scored: number
  personas: NonNullable<MatrixInput['personas']>
  student_fitted: NonNullable<MatrixInput['student_fitted']>
  ctx: Record<'spread_bucket' | 'close' | 'blowout' | 'div_game' | 'primetime' | 'dome' | 'month' | 'home_fav', Float64Array>
}

const cache = new WeakMap<object, Prepared>()

/** JSON-shaped matrix -> typed arrays, sorted by season (stable). Cached per matrix object. */
export function prepare(m: MatrixInput): Prepared {
  const hit = cache.get(m)
  if (hit) return hit
  const cols = m.columns as Record<string, Col | undefined>
  const seasonCol = cols.season as readonly number[]
  const n = seasonCol.length
  const order = Array.from({ length: n }, (_, i) => i).sort((a, b) => seasonCol[a] - seasonCol[b] || a - b)
  const f64 = (name: string): Float64Array => {
    const c = cols[name]
    const out = new Float64Array(n)
    for (let i = 0; i < n; i++) {
      const v = c ? c[order[i]] : null
      out[i] = v == null ? NaN : Number(v)
    }
    return out
  }
  const groups = [...m.groups]
  const G = groups.length
  const C = new Float64Array(n * G)
  groups.forEach((g, j) => {
    const col = m.c[g]
    for (let i = 0; i < n; i++) C[i * G + j] = col[order[i]]
  })
  const season = Int32Array.from(order, (o) => seasonCol[o])
  const warmup = new Uint8Array(n)
  if (cols.warmup) for (let i = 0; i < n; i++) warmup[i] = Number(cols.warmup[order[i]]) ? 1 : 0
  let first = m.first_scored
  if (first == null) {
    first = Infinity
    for (let i = 0; i < n; i++) if (!warmup[i] && season[i] < first) first = season[i]
  }
  const gid = cols.game_id as readonly string[] | undefined
  const out: Prepared = {
    n, groups, inactive: [...(m.inactive ?? [])], C, season, warmup,
    y: f64('y'), mkt: f64('mkt_p'), result: f64('result'), home_ml: f64('home_ml'), away_ml: f64('away_ml'),
    week: f64('week'),
    game_id: Array.from({ length: n }, (_, i) => (gid ? gid[order[i]] : String(i))),
    first_scored: first,
    personas: m.personas ?? {},
    student_fitted: m.student_fitted ?? {},
    ctx: {
      spread_bucket: f64('spread_bucket'), close: f64('close'), blowout: f64('blowout'), div_game: f64('div_game'),
      primetime: f64('primetime'), dome: f64('dome'), month: f64('month'), home_fav: f64('home_fav'),
    },
  }
  cache.set(m, out)
  return out
}

// ------------------------------------------------------------------------------------ estimators

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))
const logaddexp0 = (x: number) => Math.max(x, 0) + Math.log1p(Math.exp(-Math.abs(x)))

/** p = σ(a·x + c) by maximum likelihood, damped Newton, slope constrained to a ≥ 0 (`_platt`). */
export function platt(x: ArrayLike<number>, y: ArrayLike<number>): [number, number] {
  const n = y.length
  if (n === 0) return [1, 0]
  let ysum = 0
  for (let i = 0; i < n; i++) ysum += y[i]
  const ybar = Math.min(Math.max(ysum / n, 1e-6), 1 - 1e-6)
  const c0 = Math.log(ybar / (1 - ybar))
  let xm = 0
  for (let i = 0; i < n; i++) xm += x[i]
  xm /= n
  let v = 0
  for (let i = 0; i < n; i++) v += (x[i] - xm) ** 2
  if (Math.sqrt(v / n) < 1e-12) return [0, c0]

  const nll = (a: number, c: number) => {
    let s = 0
    for (let i = 0; i < n; i++) {
      const eta = a * x[i] + c
      s += logaddexp0(eta) - y[i] * eta
    }
    return s
  }
  let a = 1
  let c = 0
  let cur = nll(a, c)
  for (let it = 0; it < 30; it++) {
    let g0 = 0, g1 = 0, h00 = 0, h01 = 0, h11 = 0
    for (let i = 0; i < n; i++) {
      const p = sigmoid(a * x[i] + c)
      const r = p - y[i]
      const w = p * (1 - p)
      g0 += r * x[i]
      g1 += r
      h00 += w * x[i] * x[i]
      h01 += w * x[i]
      h11 += w
    }
    h00 += 1e-8
    h11 += 1e-8
    const det = h00 * h11 - h01 * h01
    const s0 = (h11 * g0 - h01 * g1) / det
    const s1 = (h00 * g1 - h01 * g0) / det
    let s = 1
    let ok = false
    let ca = a, cc = c, val = cur
    while (s > 1e-4) {
      ca = a - s * s0
      cc = c - s * s1
      val = nll(ca, cc)
      if (val <= cur + 1e-12) { ok = true; break }
      s /= 2
    }
    if (!ok) break
    const done = Math.abs(cur - val) < 1e-10
    a = ca; c = cc; cur = val
    if (done) break
  }
  return a < 0 ? [0, c0] : [a, c]
}

export type PlattParams = Record<number, [a: number, c: number, inSample: boolean]>

/** Calibrated logit per row. Season S uses only rows of earlier seasons (itself if none: flagged). */
export function walkForwardPlatt(
  logit: Float64Array, y: Float64Array, season: Int32Array, scored: number[], rows?: Uint8Array,
): { out: Float64Array; params: PlattParams } {
  const n = logit.length
  const out = logit.slice()
  const params: PlattParams = {}
  for (const s of scored) {
    const prior: number[] = []
    const cur: number[] = []
    for (let i = 0; i < n; i++) {
      if (rows && !rows[i]) continue
      if (season[i] < s) prior.push(i)
      else if (season[i] === s) cur.push(i)
    }
    const inSample = prior.length === 0
    const win = inSample ? cur : prior
    const [a, c] = platt(win.map((i) => logit[i]), win.map((i) => y[i]))
    for (const i of cur) out[i] = a * logit[i] + c
    params[s] = [a, c, inSample]
  }
  return { out, params }
}

/** The weight vector for season s: a per-season set uses that season's entry, else the earliest. */
export function seasonWeights(weights: Weights, s: number, groups: string[]): Float64Array {
  let w: GroupWeights
  if (isPerSeason(weights)) {
    const keys = Object.keys(weights)
    w = weights[String(s)] ?? weights[keys.reduce((m, k) => (Number(k) < Number(m) ? k : m))]
  } else w = weights
  return Float64Array.from(groups, (g) => w[g] ?? 0)
}

/** Σ_g W_g c_g per row (`_raw_logit`); per-season sets apply each season's own weights. */
export function rawLogit(P: Prepared, weights: Weights): Float64Array {
  const G = P.groups.length
  const out = new Float64Array(P.n)
  const cache = new Map<number, Float64Array>()
  for (let i = 0; i < P.n; i++) {
    const s = P.season[i]
    let wv = cache.get(s)
    if (!wv) { wv = seasonWeights(weights, s, P.groups); cache.set(s, wv) }
    let t = 0
    for (let j = 0; j < G; j++) t += P.C[i * G + j] * wv[j]
    out[i] = t
  }
  return out
}

export interface SeasonPredictions {
  game_id: string[]
  p: Float64Array
  calib_a: number
  calib_c: number
}

/** Per-game calibrated p(home) for one season, exactly as `evaluate` computes it (`season_predictions`). */
export function seasonPredictions(weights: Weights, matrix: MatrixInput, season: number): SeasonPredictions {
  const P = prepare(matrix)
  const raw = rawLogit(P, weights)
  const rows = new Uint8Array(P.n)
  for (let i = 0; i < P.n; i++) rows[i] = P.season[i] <= season ? 1 : 0
  const { out, params } = walkForwardPlatt(raw, P.y, P.season, [season], rows)
  const ids: string[] = []
  const p: number[] = []
  for (let i = 0; i < P.n; i++) if (P.season[i] === season) { ids.push(P.game_id[i]); p.push(sigmoid(out[i])) }
  const [calib_a, calib_c] = params[season] ?? [NaN, NaN]
  return { game_id: ids, p: Float64Array.from(p), calib_a, calib_c }
}

// ------------------------------------------------------------------------------------- evaluate

export interface KeyGame {
  game_id: string
  week: number | null
  home_won: number
  p: number
  market_p: number | null
  delta: number
  group: string
  group_logit: number
}
export interface SeasonResult {
  season: number
  n: number
  log_loss: number
  market_log_loss: number | null
  delta: number | null
  calib_a: number
  calib_c: number
  in_sample_calibration: boolean
  key_games: KeyGame[] | null
}
export interface Bucket {
  group: string
  bucket: string
  n: number
  log_loss: number
  market_log_loss: number | null
  delta: number | null
  delta_se: number | null
}
export interface DivergenceRow {
  bucket: string
  n: number
  lean_win_rate: number | null
  market_expected_rate: number | null
  log_loss: number | null
  market_log_loss: number | null
}
export interface Evaluation {
  overall: {
    n: number
    seasons: number
    log_loss: number | null
    ll_lo: number
    ll_hi: number
    market_log_loss: number | null
    delta: number | null
    d_lo: number
    d_hi: number
    accuracy: number | null
    market_accuracy: number | null
    n_market: number
  }
  seasons: SeasonResult[]
  best: SeasonResult[]
  worst: SeasonResult[]
  aging: { slope: number | null; slope_lo: number | null; slope_hi: number | null; per_decade?: number; sentence: string }
  by_context: Bucket[]
  divergence: DivergenceRow[]
  bets: { n: number; wins: number; losses: number; units: number; roi: number | null; by_season: Record<number, number> }
  reliability: { bin: number; n: number; mean_p: number; hit_rate: number }[]
  inactive: string[]
  scored_seasons: number[]
  first_season_in_sample: boolean
}

function clipLL(p: number, y: number): number {
  const q = Math.min(Math.max(p, EPS), 1 - EPS)
  return -(y * Math.log(q) + (1 - y) * Math.log(1 - q))
}

const mean = (a: ArrayLike<number>) => {
  let s = 0
  for (let i = 0; i < a.length; i++) s += a[i]
  return s / a.length
}

function bootRatio(num: number[], den: number[], rng: () => number): [number, number] {
  const k = num.length
  if (k < 2) return [NaN, NaN]
  const b = new Float64Array(BOOTSTRAP)
  for (let r = 0; r < BOOTSTRAP; r++) {
    let sn = 0, sd = 0
    for (let t = 0; t < k; t++) {
      const i = Math.floor(rng() * k)
      sn += num[i]
      sd += den[i]
    }
    b[r] = sn / sd
  }
  return [nanQuantile(b, 0.05), nanQuantile(b, 0.95)]
}

const signed3 = (x: number) => `${x < 0 ? '-' : '+'}${Math.abs(x).toFixed(3)}`

function aging(ds: [number, number][], rng: () => number): Evaluation['aging'] {
  if (ds.length < 4) return { slope: null, slope_lo: null, slope_hi: null, sentence: 'Too few seasons.' }
  const slope = (x: ArrayLike<number>, d: ArrayLike<number>) => {
    const xm = mean(x), dm = mean(d)
    let num = 0, den = 0
    for (let i = 0; i < x.length; i++) { num += (x[i] - xm) * (d[i] - dm); den += (x[i] - xm) ** 2 }
    return num / den
  }
  const x = ds.map((r) => r[0])
  const d = ds.map((r) => r[1])
  const sl = slope(x, d)
  const k = x.length
  const b = new Float64Array(BOOTSTRAP)
  for (let r = 0; r < BOOTSTRAP; r++) {
    const bx = new Float64Array(k), bd = new Float64Array(k)
    for (let t = 0; t < k; t++) { const i = Math.floor(rng() * k); bx[t] = x[i]; bd[t] = d[i] }
    b[r] = slope(bx, bd)
  }
  const lo = nanQuantile(b, 0.05), hi = nanQuantile(b, 0.95)
  const dec = sl * 10
  const ci = `(90% CI ${signed3(lo * 10)} to ${signed3(hi * 10)}`
  let sentence: string
  if (lo > 0) sentence = `Your weights have been fading relative to the market: Δ log loss is rising ${signed3(dec)} per decade ${ci}).`
  else if (hi < 0) sentence = `Your weights have been improving relative to the market: Δ log loss is falling ${signed3(dec)} per decade ${ci}).`
  else sentence = `No clear trend against the market: ${signed3(dec)} per decade ${ci} includes zero).`
  return { slope: sl, slope_lo: lo, slope_hi: hi, per_decade: dec, sentence }
}

function bucketTable(label: string, codes: Float64Array, names: [number, string][], use: Uint8Array, ll: Float64Array, mll: Float64Array): Bucket[] {
  const rows: Bucket[] = []
  for (const [code, name] of names) {
    let n = 0, sl = 0
    const d: number[] = []
    let sm = 0
    for (let i = 0; i < codes.length; i++) {
      if (!use[i] || codes[i] !== code) continue
      n++
      sl += ll[i]
      if (!Number.isNaN(mll[i])) { d.push(ll[i] - mll[i]); sm += mll[i] }
    }
    if (!n) continue
    const dm = d.length ? d.reduce((a, v) => a + v, 0) / d.length : NaN
    let se: number | null = null
    if (d.length > 1) {
      const v = d.reduce((a, t) => a + (t - dm) ** 2, 0) / (d.length - 1)
      se = Math.sqrt(v) / Math.sqrt(d.length)
    }
    rows.push({
      group: label, bucket: name, n, log_loss: sl / n,
      market_log_loss: d.length ? sm / d.length : null,
      delta: d.length ? dm : null, delta_se: se,
    })
  }
  return rows
}

function topGames(P: Prepared, rows: number[], p: Float64Array, ll: Float64Array, mll: Float64Array, a: number, W: Float64Array, worse: boolean): KeyGame[] {
  const G = P.groups.length
  const d = rows.map((i) => (Number.isNaN(mll[i]) ? 0 : ll[i] - mll[i]))
  const order = d.map((_, k) => k).sort((x, y) => (worse ? d[y] - d[x] : d[x] - d[y]) || x - y).slice(0, 3)
  return order.map((o) => {
    const i = rows[o]
    let j = 0, best = -1, gl = 0
    for (let g = 0; g < G; g++) {
      const t = a * W[g] * P.C[i * G + g]
      if (Math.abs(t) > best) { best = Math.abs(t); j = g; gl = t }
    }
    return {
      game_id: P.game_id[i],
      week: Number.isNaN(P.week[i]) ? null : Math.trunc(P.week[i]),
      home_won: P.y[i], p: p[i],
      market_p: Number.isNaN(P.mkt[i]) ? null : P.mkt[i],
      delta: d[o], group: P.groups[j], group_logit: gl,
    }
  })
}

export interface EvalOptions {
  /** exclude later seasons from everything (the "hide the last 3 seasons" toggle) */
  maxSeason?: number | null
  seed?: number
}

/** Score group weights over the matrix (`evaluate`). */
export function evaluate(weights: Weights, matrix: MatrixInput, opts: EvalOptions = {}): Evaluation {
  const P = prepare(matrix)
  const { n, season, y } = P
  const max = opts.maxSeason ?? null
  const scoredSet = new Set<number>()
  for (let i = 0; i < n; i++) if (!P.warmup[i] && (max == null || season[i] <= max)) scoredSet.add(season[i])
  const scored = [...scoredSet].sort((a, b) => a - b)
  const use = new Uint8Array(n)
  const keep = new Uint8Array(n)
  const first = scored.length ? scored[0] : 0
  for (let i = 0; i < n; i++) {
    use[i] = !P.warmup[i] && scoredSet.has(season[i]) ? 1 : 0
    keep[i] = scoredSet.has(season[i]) || (P.warmup[i] && season[i] < first) ? 1 : 0
  }
  const raw = rawLogit(P, weights)
  const { out, params } = walkForwardPlatt(raw, y, season, scored, keep)
  const p = new Float64Array(n)
  const ll = new Float64Array(n)
  const mll = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    p[i] = keep[i] ? sigmoid(out[i]) : 0.5
    ll[i] = clipLL(p[i], y[i])
    mll[i] = Number.isNaN(P.mkt[i]) ? NaN : clipLL(P.mkt[i], y[i])
  }
  const rng = mulberry32(opts.seed ?? 0)

  const nS: number[] = [], llS: number[] = [], dS: number[] = [], npS: number[] = []
  const seasons: SeasonResult[] = []
  for (const s of scored) {
    let m = 0, mp = 0, sl = 0, sd = 0, sm = 0
    for (let i = 0; i < n; i++) {
      if (season[i] !== s) continue
      m++
      sl += ll[i]
      if (!Number.isNaN(mll[i])) { mp++; sd += ll[i] - mll[i]; sm += mll[i] }
    }
    nS.push(m); llS.push(sl); dS.push(sd); npS.push(mp)
    const [a, c, ins] = params[s]
    seasons.push({
      season: s, n: m, log_loss: sl / m,
      market_log_loss: mp ? sm / mp : null, delta: mp ? sd / mp : null,
      calib_a: a, calib_c: c, in_sample_calibration: ins, key_games: null,
    })
  }
  const sum = (a: number[]) => a.reduce((x, v) => x + v, 0)
  const [lo, hi] = bootRatio(llS, nS, rng)
  const [dlo, dhi] = bootRatio(dS, npS, rng)

  // market log loss, accuracy and reliability bins over the scored, market-priced games
  let mSum = 0, mN = 0, right = 0, mRight = 0, nUse = 0
  const bins = Array.from({ length: 10 }, () => ({ n: 0, sp: 0, sy: 0 }))
  for (let i = 0; i < n; i++) {
    if (!use[i]) continue
    nUse++
    if ((p[i] >= 0.5) === (y[i] === 1)) right++
    const b = bins[Math.min(Math.floor(p[i] * 10), 9)]
    b.n++; b.sp += p[i]; b.sy += y[i]
    if (!Number.isNaN(mll[i])) { mSum += mll[i]; mN++; if ((P.mkt[i] >= 0.5) === (y[i] === 1)) mRight++ }
  }
  const nTot = sum(nS), nPTot = sum(npS)
  const overall: Evaluation['overall'] = {
    n: nTot, seasons: scored.length,
    log_loss: nTot ? sum(llS) / nTot : null, ll_lo: lo, ll_hi: hi,
    market_log_loss: mN ? mSum / mN : null,
    delta: nPTot ? sum(dS) / nPTot : null, d_lo: dlo, d_hi: dhi,
    accuracy: nUse ? right / nUse : null, market_accuracy: mN ? mRight / mN : null, n_market: mN,
  }

  // best and worst seasons, with the games that moved them
  const Wv = scored.map((s) => seasonWeights(weights, s, P.groups))
  const ranked = seasons.filter((r) => r.delta != null).sort((a, b) => (a.delta as number) - (b.delta as number))
  const best = ranked.slice(0, 3)
  const worst = ranked.slice(-3).reverse()
  for (const [list, worse] of [[best, false], [worst, true]] as const) {
    for (const r of list) {
      const rows: number[] = []
      for (let i = 0; i < n; i++) if (season[i] === r.season) rows.push(i)
      r.key_games = topGames(P, rows, p, ll, mll, r.calib_a, Wv[scored.indexOf(r.season)], worse)
    }
  }

  const ds = seasons.filter((r) => r.delta != null).map((r) => [r.season, r.delta as number] as [number, number])
  const ctx = P.ctx
  const by_context = [
    ...bucketTable('Spread size', ctx.spread_bucket, SPREAD_LABELS, use, ll, mll),
    ...bucketTable('Result (known after the fact)', ctx.close, [[1, 'Close (within 3)']], use, ll, mll),
    ...bucketTable('Result (known after the fact)', ctx.blowout, [[1, 'Blowout (14+)']], use, ll, mll),
    ...bucketTable('Division', ctx.div_game, [[1, 'Division game'], [0, 'Non-division']], use, ll, mll),
    ...bucketTable('Time slot', ctx.primetime, [[1, 'Primetime'], [0, 'Day games']], use, ll, mll),
    ...bucketTable('Roof', ctx.dome, [[1, 'Dome / closed roof'], [0, 'Open air']], use, ll, mll),
    ...bucketTable('Month', ctx.month, MONTH_LABELS, use, ll, mll),
    ...bucketTable('Home side', ctx.home_fav, FAV_LABELS, use, ll, mll),
  ]

  return {
    overall, seasons, best, worst, aging: aging(ds, rng), by_context,
    divergence: divergence(P, p, ll, mll, use),
    bets: bets(P, p, use),
    reliability: bins.map((b, k) => ({ bin: k, n: b.n, mean_p: b.sp / b.n, hit_rate: b.sy / b.n })).filter((b) => b.n),
    inactive: P.inactive,
    scored_seasons: scored,
    first_season_in_sample: scored.length ? params[scored[0]][2] : false,
  }
}

function divergence(P: Prepared, p: Float64Array, ll: Float64Array, mll: Float64Array, use: Uint8Array): DivergenceRow[] {
  const edges = [...DIVERGENCE_BUCKETS, Infinity]
  return DIV_LABELS.map((bucket, k) => {
    let n = 0, won = 0, exp = 0, sl = 0, sm = 0
    for (let i = 0; i < P.n; i++) {
      const mk = P.mkt[i]
      if (!use[i] || Number.isNaN(mk)) continue
      const gap = Math.abs(p[i] - mk)
      if (!(gap >= edges[k] && gap < edges[k + 1])) continue
      const home = p[i] > mk
      n++
      won += home ? P.y[i] : 1 - P.y[i]
      exp += home ? mk : 1 - mk
      sl += ll[i]
      sm += mll[i]
    }
    return {
      bucket, n,
      lean_win_rate: n ? won / n : null, market_expected_rate: n ? exp / n : null,
      log_loss: n ? sl / n : null, market_log_loss: n ? sm / n : null,
    }
  })
}

/** Flat 1-unit moneyline on the side the model likes more than the market, edge above 5 points. */
function bets(P: Prepared, p: Float64Array, use: Uint8Array): Evaluation['bets'] {
  let n = 0, wins = 0, units = 0
  const by: Record<number, number> = {}
  for (let i = 0; i < P.n; i++) {
    const mk = P.mkt[i]
    if (!use[i] || Number.isNaN(mk)) continue
    const edge = p[i] - mk
    const home = edge > 0
    const price = home ? P.home_ml[i] : P.away_ml[i]
    if (!(Math.abs(edge) > EDGE_THRESHOLD) || Number.isNaN(price)) continue
    const won = (home ? P.y[i] : 1 - P.y[i]) === 1
    const payout = price > 0 ? price / 100 : 100 / Math.abs(price === 0 ? 1 : price)
    const profit = won ? payout : -1
    n++
    if (won) wins++
    units += profit
    by[P.season[i]] = (by[P.season[i]] ?? 0) + profit
  }
  return { n, wins, losses: n - wins, units, roi: n ? units / n : null, by_season: by }
}
