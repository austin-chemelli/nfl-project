/**
 * "Fit toward you": a ridge on the composites over all scored seasons, shrunk toward the user's
 * weights (`fit_toward`). Python minimizes with L-BFGS-B; this is a damped Newton on the same
 * convex objective, so it reaches the same optimum (to well under a tenth of a share point) without
 * a numerical library.
 */
import { platt, prepare, type MatrixInput } from './evaluate'
import type { GroupWeights } from './weights'

export interface FitToward {
  weights: GroupWeights
  user_scaled: GroupWeights
  intercept: number
  lam: number
  /** signed shares of a 100-point budget */
  shares: GroupWeights
  user_shares: GroupWeights
}

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))
const logaddexp0 = (x: number) => Math.max(x, 0) + Math.log1p(Math.exp(-Math.abs(x)))

/** Solve A x = b (A symmetric positive definite, row-major) by Cholesky. */
function solveSPD(A: Float64Array, b: Float64Array, k: number): Float64Array {
  const L = new Float64Array(k * k)
  for (let i = 0; i < k; i++) {
    for (let j = 0; j <= i; j++) {
      let s = A[i * k + j]
      for (let t = 0; t < j; t++) s -= L[i * k + t] * L[j * k + t]
      L[i * k + j] = i === j ? Math.sqrt(Math.max(s, 1e-12)) : s / L[j * k + j]
    }
  }
  const z = new Float64Array(k)
  for (let i = 0; i < k; i++) {
    let s = b[i]
    for (let t = 0; t < i; t++) s -= L[i * k + t] * z[t]
    z[i] = s / L[i * k + i]
  }
  const x = new Float64Array(k)
  for (let i = k - 1; i >= 0; i--) {
    let s = z[i]
    for (let t = i + 1; t < k; t++) s -= L[t * k + i] * x[t]
    x[i] = s / L[i * k + i]
  }
  return x
}

/** Logistic regression with penalty λ‖w − w0‖² and a free intercept. Returns [b, w]. */
export function fitRidge(z: Float64Array, y: Float64Array, k: number, w0: Float64Array, lam: number, b0: number): [number, Float64Array] {
  const n = y.length
  const d = k + 1
  const t = new Float64Array(d)
  t[0] = b0
  t.set(w0, 1)
  const objective = (th: Float64Array) => {
    let s = 0
    for (let i = 0; i < n; i++) {
      let eta = th[0]
      for (let j = 0; j < k; j++) eta += z[i * k + j] * th[j + 1]
      s += logaddexp0(eta) - y[i] * eta
    }
    for (let j = 0; j < k; j++) s += lam * (th[j + 1] - w0[j]) ** 2
    return s
  }
  let cur = objective(t)
  for (let it = 0; it < 100; it++) {
    const g = new Float64Array(d)
    const H = new Float64Array(d * d)
    for (let i = 0; i < n; i++) {
      let eta = t[0]
      for (let j = 0; j < k; j++) eta += z[i * k + j] * t[j + 1]
      const p = sigmoid(eta)
      const r = p - y[i]
      const w = p * (1 - p)
      g[0] += r
      H[0] += w
      for (let a = 0; a < k; a++) {
        const za = z[i * k + a]
        g[a + 1] += za * r
        H[a + 1] += w * za
        for (let c = 0; c <= a; c++) H[(a + 1) * d + c + 1] += w * za * z[i * k + c]
      }
    }
    for (let a = 0; a < k; a++) {
      g[a + 1] += 2 * lam * (t[a + 1] - w0[a])
      H[(a + 1) * d + a + 1] += 2 * lam
      H[(a + 1) * d] = H[a + 1]
    }
    for (let a = 0; a < d; a++) for (let c = a + 1; c < d; c++) H[a * d + c] = H[c * d + a]
    let gmax = 0
    for (let a = 0; a < d; a++) gmax = Math.max(gmax, Math.abs(g[a]))
    if (gmax < 1e-8) break
    const step = solveSPD(H, g, d)
    let s = 1
    let moved = false
    while (s > 1e-6) {
      const cand = t.map((v, a) => v - s * step[a])
      const val = objective(cand)
      if (val <= cur) { t.set(cand); cur = val; moved = true; break }
      s /= 2
    }
    if (!moved) break
  }
  return [t[0], t.slice(1)]
}

export function fitToward(weights: GroupWeights, matrix: MatrixInput, opts: { lam?: number; maxSeason?: number | null } = {}): FitToward {
  const lam = opts.lam ?? 1250
  const P = prepare(matrix)
  const maxSeason = opts.maxSeason || 1e9
  const groups = P.groups.filter((g) => !P.inactive.includes(g))
  const cols = groups.map((g) => P.groups.indexOf(g))
  const G = P.groups.length
  const rows: number[] = []
  for (let i = 0; i < P.n; i++) if (!P.warmup[i] && P.season[i] <= maxSeason) rows.push(i)
  const k = groups.length
  const z = new Float64Array(rows.length * k)
  const y = new Float64Array(rows.length)
  rows.forEach((i, r) => {
    y[r] = P.y[i]
    cols.forEach((c, j) => { z[r * k + j] = P.C[i * G + c] })
  })
  const wUser = Float64Array.from(groups, (g) => weights[g] ?? 0)
  const x = new Float64Array(rows.length)
  for (let r = 0; r < rows.length; r++) {
    let s = 0
    for (let j = 0; j < k; j++) s += z[r * k + j] * wUser[j]
    x[r] = s
  }
  const [a, c] = platt(x, y)
  const w0 = wUser.map((v) => a * v)
  const [b, w] = fitRidge(z, y, k, w0, lam, c)
  const share = (v: Float64Array): GroupWeights => {
    let tot = 0
    for (const t of v) tot += Math.abs(t)
    return Object.fromEntries(groups.map((g, j) => [g, tot > 0 ? (100 * v[j]) / tot : 0]))
  }
  const rec = (v: Float64Array): GroupWeights => Object.fromEntries(groups.map((g, j) => [g, v[j]]))
  return { weights: rec(w), user_scaled: rec(w0), intercept: b, lam, shares: share(w), user_shares: share(w0) }
}
