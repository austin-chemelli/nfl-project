/** Pure helpers for the Hypotheses page. Only the *_pp fields are used; logit fields never surface. */
import type { Hypotheses } from '../../data/contract'

export type Feature = Hypotheses['features'][number]
export type Item = Hypotheses['by_season']['items'][string]
export type SeasonPoint = Item['series'][number]

export const UNGROUPED = 'Not in a group'
export const VERDICTS = ['matters', 'weak', 'no evidence'] as const
export const VERDICT_NOTE: Record<string, string> = {
  matters: 'the 90% range excludes zero and the effect is at least 0.75 points per +1 SD',
  weak: 'a small effect with a clear interval, or one bigger than its noise but not clear',
  'no evidence': 'indistinguishable from zero',
}
/** Color carries the verdict next to the badge text (never the only cue). */
export const VERDICT_COLOR: Record<string, string> = {
  matters: 'var(--accent)',
  weak: 'var(--series-ref)',
  'no evidence': 'var(--border)',
}

type GroupLookup = (id: string) => string | undefined

export function groupLabel(f: Feature, name: GroupLookup): string {
  if (!f.group) return UNGROUPED
  return name(f.group) ?? f.group.replace(/_/g, ' ')
}

/** Group filter ('' = all) and verdict filter ('' = all). */
export function filterFeatures(feats: Feature[], name: GroupLookup, group: string, verdict: string): Feature[] {
  return feats.filter((f) => (!group || groupLabel(f, name) === group) && (!verdict || f.verdict === verdict))
}

/** Grouped by group name (ungrouped last), largest absolute effect first within a group. */
export function sortFeatures(feats: Feature[], name: GroupLookup): Feature[] {
  return [...feats].sort((a, b) => {
    const ga = groupLabel(a, name)
    const gb = groupLabel(b, name)
    if ((ga === UNGROUPED) !== (gb === UNGROUPED)) return ga === UNGROUPED ? 1 : -1
    return ga.localeCompare(gb) || Math.abs(b.effect_pp) - Math.abs(a.effect_pp)
  })
}

export function verdictCounts(feats: Feature[]): Record<string, number> {
  return Object.fromEntries(VERDICTS.map((v) => [v, feats.filter((f) => f.verdict === v).length]))
}

export function pp(x: number, digits = 2): string {
  return `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(digits)}`
}

export function itemName(it: Item): string {
  return it.kind === 'group' ? `${it.label} (group)` : it.label
}

/** Groups first, then features, each alphabetical. */
export function itemOptions(items: Record<string, Item>): { key: string; name: string; kind: string }[] {
  return Object.entries(items)
    .map(([key, it]) => ({ key, name: itemName(it), kind: it.kind }))
    .sort((a, b) => Number(a.kind !== 'group') - Number(b.kind !== 'group') || a.name.toLowerCase().localeCompare(b.name.toLowerCase()))
}

export function searchOptions<T extends { name: string }>(opts: T[], q: string): T[] {
  const s = q.trim().toLowerCase()
  return s ? opts.filter((o) => o.name.toLowerCase().includes(s)) : opts
}

/** The `?item=` value if it names a real item, else the default (quality group, else the first). */
export function resolveItem(items: Record<string, Item>, requested: string | null): string | null {
  if (requested && requested in items) return requested
  if ('group:quality' in items) return 'group:quality'
  return itemOptions(items)[0]?.key ?? null
}

export type ChartRow = { season: number; edge: number | null; skill: number | null; nEdge: number; nGames: number }

/** One row per season from first_scored to the last season; seasons with no data get nulls (gaps). */
export function chartRows(it: Item, firstScored: number): ChartRow[] {
  const by = new Map(it.series.map((p) => [p.season, p]))
  const last = Math.max(firstScored, ...it.series.map((p) => p.season))
  const rows: ChartRow[] = []
  for (let s = firstScored; s <= last; s++) {
    const p = by.get(s)
    rows.push({
      season: s,
      edge: p?.edge_win_rate == null ? null : 100 * p.edge_win_rate,
      skill: p?.skill_pct ?? null,
      nEdge: p?.n_edge ?? 0,
      nGames: p?.n_games ?? 0,
    })
  }
  return rows
}

/** Best and worst season by improvement over the baseline; the file's own pick wins when present. */
export function bestWorst(it: Item): { best: number | null; worst: number | null } {
  const pooled = it.pooled
  const scored = it.series.filter((p) => p.skill_pct != null)
  const by = (cmp: (a: number, b: number) => boolean) =>
    scored.reduce<SeasonPoint | null>((m, p) => (m == null || cmp(p.skill_pct as number, m.skill_pct as number) ? p : m), null)?.season ?? null
  return {
    best: pooled.best_season ?? by((a, b) => a > b),
    worst: pooled.worst_season ?? by((a, b) => a < b),
  }
}

export function skillText(x: number | null | undefined): string {
  return x == null ? '–' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(1)}%`
}
