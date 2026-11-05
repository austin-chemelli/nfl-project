/**
 * The ensemble is a diagnostic, not a site line (D5, Austin 2026-11-04), but its rows stay in the
 * data until wave 2 stops locking it, and retros and recaps built before then still rank it. The
 * contract runs every file through these at load, so no page ever sees it. Each one is a no-op on
 * data without the ensemble; delete this file once the published data has none left.
 */
const ID = 'ensemble'

const mentions = (s: string) => /\bensemble\b/i.test(s)
const drop = <T extends { model_id: string }>(rows: T[]) => rows.filter((r) => r.model_id !== ID)
const omit = <V>(rec: Record<string, V>): Record<string, V> => Object.fromEntries(Object.entries(rec).filter(([k]) => k !== ID))

export const hideInGameRow = <T extends { models: Record<string, unknown> }>(g: T): T => ({ ...g, models: omit(g.models) })

export const hideInSlate = <G extends { models: Record<string, unknown> }, T extends { games: G[] }>(s: T): T => ({
  ...s,
  games: s.games.map(hideInGameRow),
})

export const hideInGame = <T extends { models: Record<string, unknown>; contributions: Record<string, unknown> }>(g: T): T => ({
  ...g,
  models: omit(g.models),
  contributions: omit(g.contributions),
})

type Pick = { model_id: string; kind: string; log_loss: number; best: boolean }

/** When the ensemble was the game's best read, the best approach takes the flag, and the headline that named it goes. */
export function hideInRetro<
  P extends Pick,
  A extends { model_id: string },
  T extends { predictions: P[]; attribution: A[]; best_model: string | null; headlines: string[] },
>(r: T): T {
  const out = { ...r, predictions: drop(r.predictions), attribution: drop(r.attribution), headlines: r.headlines.filter((h) => !mentions(h)) }
  if (r.best_model !== ID) return out
  const best = out.predictions.filter((p) => p.kind === 'approach').reduce<P | null>((a, p) => (a == null || p.log_loss < a.log_loss ? p : a), null)
  return { ...out, best_model: best?.model_id ?? null, predictions: out.predictions.map((p) => ({ ...p, best: p.model_id === best?.model_id })) }
}

/** Ranks close up behind the ensemble. "Most misread" rows built on it go; `retro/week.py` now uses the Student, so they return with each rebuilt recap. */
export function hideInRecap<
  M extends { model_id: string; rank: number },
  G extends { sentence: string },
  T extends { models: M[]; best_model: string | null; misread: G[] },
>(r: T): T {
  const models = drop(r.models)
  const ranked = models.filter((m) => m.rank > 0).sort((a, b) => a.rank - b.rank)
  return {
    ...r,
    models: models.map((m) => (m.rank > 0 ? { ...m, rank: ranked.indexOf(m) + 1 } : m)),
    best_model: r.best_model === ID ? (ranked[0]?.model_id ?? null) : r.best_model,
    misread: r.misread.filter((x) => !mentions(x.sentence)),
  }
}

export const hideInTracker = <
  T extends Record<'seasons' | 'current_season' | 'backtest' | 'reliability' | 'divergence' | 'ledger', { model_id: string }[]>,
>(t: T): T => ({
  ...t,
  seasons: drop(t.seasons),
  current_season: drop(t.current_season),
  backtest: drop(t.backtest),
  reliability: drop(t.reliability),
  divergence: drop(t.divergence),
  ledger: drop(t.ledger),
})
