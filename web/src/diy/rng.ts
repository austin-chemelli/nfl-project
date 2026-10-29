/**
 * Seeded generator for the bootstrap confidence intervals. numpy's PCG64 stream cannot be
 * reproduced cheaply in the browser, so intervals differ from Python's in the last digits (they
 * estimate the same quantiles; the point estimates match exactly). Tests only check them loosely.
 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** numpy's default ("linear") quantile of the finite values; NaN when there are none. */
export function nanQuantile(values: ArrayLike<number>, q: number): number {
  const a: number[] = []
  for (let i = 0; i < values.length; i++) if (!Number.isNaN(values[i])) a.push(values[i])
  if (!a.length) return NaN
  a.sort((x, y) => x - y)
  const pos = q * (a.length - 1)
  const lo = Math.floor(pos)
  const hi = Math.min(lo + 1, a.length - 1)
  return a[lo] + (a[hi] - a[lo]) * (pos - lo)
}
