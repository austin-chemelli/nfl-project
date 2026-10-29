/** Pure helpers for the Tracker page (ports of src/nfl/ui/tracker_helpers.py). */
import type { Approach, Tracker } from '../../data/contract'
import { llVsMarket } from '../../lib/format'

/** Log-loss differences below this are indistinguishable at these sample sizes. */
export const NOISE = 0.005
export const BUCKET_ORDER = ['0-2.5', '2.5-5', '5-10', '10+']
export const BUCKET_WORDS: Record<string, string> = {
  '0-2.5': 'by less than 2.5 points',
  '2.5-5': 'by 2.5 to 5 points',
  '5-10': 'by 5 to 10 points',
  '10+': 'by 10+ points',
}

type Reliability = Tracker['reliability'][number]
type Divergence = Tracker['divergence'][number]
export type FoldedBin = { mean_p: number; hit_rate: number; n: number }

/** 'The Traditionalist' -> 'the Traditionalist' for mid-sentence use. */
export function shortName(name: string): string {
  return name.startsWith('The ') ? name[0].toLowerCase() + name.slice(1) : name
}

/** Re-express home-win bins as "the favored side": mirrored bins (25% home / 75% home) are pooled. */
export function foldReliability(rows: Pick<Reliability, 'mean_p' | 'hit_rate' | 'n'>[]): FoldedBin[] {
  const pooled = new Map<number, { p: number; h: number; n: number }>()
  for (const r of rows) {
    let p = r.mean_p
    let h = r.hit_rate
    if (p < 0.5) {
      p = 1 - p
      h = 1 - h
    }
    const k = p < 0.95 ? Math.round(p * 10) : 10 // tenth-wide cells: 5 = 50-55 ... 9 = 85-95
    const c = pooled.get(k) ?? { p: 0, h: 0, n: 0 }
    c.p += p * r.n
    c.h += h * r.n
    c.n += r.n
    pooled.set(k, c)
  }
  return [...pooled.entries()]
    .sort((a, b) => a[0] - b[0])
    .filter(([, c]) => c.n > 0)
    .map(([, c]) => ({ mean_p: c.p / c.n, hit_rate: c.h / c.n, n: c.n }))
}

export type Verdict = { kind: 'well' | 'over' | 'under' | 'few'; gapPts: number; said: number; won: number; n: number; text: string }

/** The gap on an approach's ~70% calls (60-80% window, both sides pooled), as one sentence. */
export function calibrationVerdict(rows: Reliability[], name: string): Verdict {
  const bins = foldReliability(rows).filter((r) => r.mean_p >= 0.6 && r.mean_p < 0.8)
  const n = bins.reduce((s, r) => s + r.n, 0)
  if (n < 50) return { kind: 'few', gapPts: 0, said: 0, won: 0, n, text: `${name}: too few 60-80% calls to judge.` }
  const said = bins.reduce((s, r) => s + r.mean_p * r.n, 0) / n
  const won = bins.reduce((s, r) => s + r.hit_rate * r.n, 0) / n
  const gap = won - said
  const gapPts = Math.round(Math.abs(gap) * 100)
  const calls = `its ${(100 * said).toFixed(0)}% calls won ${(100 * won).toFixed(0)}% (n = ${n.toLocaleString('en-US')})`
  if (gap < -0.03) return { kind: 'over', gapPts, said, won, n, text: `${name}: overconfident by ${gapPts} points, ${calls}.` }
  if (gap > 0.03) return { kind: 'under', gapPts, said, won, n, text: `${name}: underconfident by ${gapPts} points, ${calls}.` }
  return { kind: 'well', gapPts, said, won, n, text: `${name}: well calibrated, ${calls}.` }
}

/** 'In 1,158 games where the Traditionalist disagreed with the market by 10+ points, its side won 40% ...' */
export function divergenceSentence(row: Pick<Divergence, 'bucket' | 'n' | 'lean_win_rate' | 'market_expected_rate'>, name: string): string {
  const words = BUCKET_WORDS[row.bucket] ?? `by ${row.bucket} points`
  const pc = (v: number | null) => (v == null ? '–' : `${(100 * v).toFixed(0)}%`)
  return (
    `In ${row.n.toLocaleString('en-US')} games where ${name} disagreed with the market ${words}, its side ` +
    `won ${pc(row.lean_win_rate)} of the time; the market expected ${pc(row.market_expected_rate)}.`
  )
}

/** (# approach-buckets where the market scored better, # checked) over the 5+ point buckets. */
export function marketWinsWhenApart(rows: Divergence[]): [number, number] {
  const big = rows.filter((r) => (r.bucket === '5-10' || r.bucket === '10+') && r.model_log_loss != null && r.market_log_loss != null)
  return [big.filter((r) => r.market_log_loss! < r.model_log_loss!).length, big.length]
}

/** "History would move 8 of the Traditionalist's 100 attention points; the biggest gap: Form, 15 vs 6." */
export function personaHistoryHeadline(a: Approach, groupLabel: (id: string) => string): string {
  const name = shortName(a.name)
  const P = a.persona_share
  const H = a.history_share
  let out = ''
  if (a.history_shifted_points != null) out = `History would move ${a.history_shifted_points.toFixed(0)} of ${name}'s 100 attention points`
  const ids = new Set([...Object.keys(P), ...Object.keys(H)])
  let best: string | null = null
  let bestGap = -1
  for (const k of ids) {
    const gap = Math.abs((P[k] ?? 0) - (H[k] ?? 0))
    if (gap > bestGap) [best, bestGap] = [k, gap]
  }
  if (best != null) {
    const gap = `the biggest gap: ${groupLabel(best)}, ${(P[best] ?? 0).toFixed(0)} vs ${(H[best] ?? 0).toFixed(0)}`
    out = out ? `${out}; ${gap}` : gap
  }
  return out ? `${out}.` : ''
}

export function calibrationScaleSentence(scale: number | null | undefined): string {
  if (!scale) return ''
  if (scale < 0.98) return `Its raw probabilities were about ${(100 * (1 / scale - 1)).toFixed(0)}% more confident than history supports, so they are shrunk before scoring.`
  if (scale > 1.02) return `Its raw probabilities were about ${(100 * (1 - 1 / scale)).toFixed(0)}% less confident than history supports, so they are stretched before scoring.`
  return 'Its confidence already matches history, so no rescaling was needed.'
}

export type CurrentRow = { model_id: string; games: number; logLoss: number; liveWeeks: number; vsMarket: string | null; delta: number | null }

/** Latest cumulative log loss per model, with games, live weeks and the gap to the market. */
export function currentSummary(cur: Tracker['current_season']): { rows: CurrentRow[]; liveGames: number; liveWeeks: number } {
  const byModel = new Map<string, Tracker['current_season']>()
  for (const r of cur) byModel.set(r.model_id, [...(byModel.get(r.model_id) ?? []), r])
  const last = (m: string) => [...(byModel.get(m) ?? [])].sort((a, b) => a.week - b.week).at(-1)
  const market = last('market_baseline')?.cum_log_loss
  const rows: CurrentRow[] = [...byModel.keys()].map((m) => {
    const rs = byModel.get(m)!
    const ll = last(m)!.cum_log_loss
    return {
      model_id: m,
      games: rs.reduce((s, r) => s + r.n, 0),
      logLoss: ll,
      liveWeeks: new Set(rs.filter((r) => r.live).map((r) => r.week)).size,
      vsMarket: m === 'market_baseline' || market == null ? null : llVsMarket(ll, market),
      delta: m === 'market_baseline' || market == null ? null : ll - market,
    }
  })
  const anyLive = cur.filter((r) => r.live)
  // Every model scores the same games, so count live games from one line (the reference if present).
  const ref = anyLive.some((r) => r.model_id === 'market_baseline') ? 'market_baseline' : anyLive[0]?.model_id
  return {
    rows,
    liveGames: anyLive.filter((r) => r.model_id === ref).reduce((s, r) => s + r.n, 0),
    liveWeeks: new Set(anyLive.map((r) => r.week)).size,
  }
}

/** "After 112 games, the Analyst is 0.012 worse than the market (log loss; lower is better)." */
export function headlineSentence(row: CurrentRow, name: string): string {
  const base = `After ${row.games.toLocaleString('en-US')} games, ${name} is `
  if (row.delta == null) return `${base}the reference.`
  if (Math.abs(row.delta) < NOISE) return `${base}about the same as the market (within ${NOISE} log loss, which is noise at this sample size).`
  return `${base}${Math.abs(row.delta).toFixed(3)} ${row.delta > 0 ? 'worse' : 'better'} than the market (log loss; lower is better).`
}
