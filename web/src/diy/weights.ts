/**
 * Weight sets: the `?w=` share format, the market-behavior cap, and shapes shared with the
 * evaluator. Mirrors nfl.approaches.diy (encode_weights, decode_weights, cap_market); the encoded
 * strings are byte-identical to Python's so links made by either app open in the other.
 */

/** Signed weight (or points) per group id. */
export type GroupWeights = Record<string, number>
/** One weight set for every season, or a set per season (the Student's yearly refits). */
export type Weights = GroupWeights | Record<string, GroupWeights>

/** Group order of the matrix (nfl.features.groups.GROUPS); fixes the order of the encoded string. */
export const GROUP_IDS = [
  'quality', 'offense', 'defense', 'quarterback', 'health', 'form', 'stakes', 'rest_travel',
  'venue_weather', 'coaching', 'off_scheme', 'def_scheme', 'matchups', 'market', 'buzz',
] as const

/** ADR 0013: Market behavior may take at most this share of a weight set's budget. */
export const MARKET_GROUP_CAP = 0.2

/** True for {season: {group: weight}} (every key a season number), as Python's `_raw_logit` decides. */
export function isPerSeason(w: Weights): w is Record<string, GroupWeights> {
  const keys = Object.keys(w)
  return keys.length > 0 && keys.every((k) => /^\d+$/.test(k))
}

/** Python's `format(x, 'g')`: 6 significant digits, trailing zeros dropped. */
export function fmtG(x: number): string {
  if (x === 0) return '0'
  const [mant, exp] = x.toExponential(5).split('e')
  const e = Number(exp)
  if (e < -4 || e >= 6) {
    const m = mant.includes('.') ? mant.replace(/0+$/, '').replace(/\.$/, '') : mant
    return `${m}e${e < 0 ? '-' : '+'}${String(Math.abs(e)).padStart(2, '0')}`
  }
  const f = x.toFixed(5 - e)
  return f.includes('.') ? f.replace(/0+$/, '').replace(/\.$/, '') : f
}

/** {group: signed points} -> 'quality:30,form:-10' (zeros dropped, matrix group order). */
export function encodeWeights(signed: GroupWeights): string {
  return GROUP_IDS.filter((g) => signed[g]).map((g) => `${g}:${fmtG(signed[g])}`).join(',')
}

const FLOAT = /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/

/** Inverse of `encodeWeights`; unknown groups and malformed pieces are ignored. */
export function decodeWeights(s: string | null | undefined): GroupWeights {
  const out: GroupWeights = {}
  for (const part of (s ?? '').split(',')) {
    const i = part.indexOf(':')
    const g = i < 0 ? part : part.slice(0, i)
    const v = i < 0 ? '' : part.slice(i + 1)
    if (!(GROUP_IDS as readonly string[]).includes(g) || !FLOAT.test(v)) continue
    const x = Number(v)
    if (Number.isFinite(x)) out[g] = Math.max(-100, Math.min(100, x))
  }
  return out
}

/** ADR 0013: scale Market behavior down to the cap. Returns the weights and whether it was capped. */
export function capMarket(signed: GroupWeights): [GroupWeights, boolean] {
  const m = signed.market ?? 0
  let rest = 0
  for (const [g, v] of Object.entries(signed)) if (g !== 'market') rest += Math.abs(v)
  const limit = (MARKET_GROUP_CAP / (1 - MARKET_GROUP_CAP)) * rest
  if (Math.abs(m) <= limit + 1e-12) return [{ ...signed }, false]
  return [{ ...signed, market: Math.sign(m) * limit }, true]
}

/** Signed points -> weights that sum (in magnitude) to 1, after the market cap. */
export function normalize(signed: GroupWeights): { weights: GroupWeights; total: number; capped: boolean } {
  const [capped, hit] = capMarket(signed)
  const total = Object.values(capped).reduce((a, v) => a + Math.abs(v), 0)
  const weights: GroupWeights = {}
  for (const [g, v] of Object.entries(capped)) weights[g] = total ? v / total : 0
  return { weights, total, capped: hit }
}
