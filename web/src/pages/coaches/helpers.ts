/** Pure helpers for the Coaches page (phrasing ported from the Streamlit page and nfl.coaches). */
import type { Coaches, CoachSide } from '../../data/contract'

export type MetricDef = Coaches['metrics'][string]
export type Person = Coaches['people'][number]
export type Season = CoachSide['seasons'][number]

/** Metrics shown by default for each side's trend and season table (as in the Streamlit page). */
export const KEY_METRICS: Record<'off' | 'def', string[]> = {
  off: ['pers_11_share', 'pers_heavy_share', 'time_to_throw', 'pressure_allowed_rate'],
  def: ['man_rate', 'two_high_rate', 'blitz_rate', 'pressure_rate'],
}
export const SIDE_NAME = { off: 'Offense', def: 'Defense' } as const

export function pct0(p: number | null | undefined): string {
  return p == null ? '–' : `${Math.round(100 * p)}%`
}

/** A percentile in words: "more shotgun than 88% of the league", "near the league average in ...". */
export function pctWords(p: number | null | undefined, m: MetricDef): string {
  if (p == null) return 'not enough charted plays'
  if (p >= 0.6) return `${m.hi} ${m.noun} than ${Math.round(100 * p)}% of the league`
  if (p <= 0.4) return `${m.lo} ${m.noun} than ${Math.round(100 * (1 - p))}% of the league`
  return `near the league average in ${m.noun}`
}

/** Metrics of one side and kind, in the order the file lists them. */
export function metricsFor(metrics: Coaches['metrics'], side: 'off' | 'def', kind?: string): [string, MetricDef][] {
  return Object.entries(metrics).filter(([, d]) => d.side === side && (!kind || d.kind === kind))
}

export function lastStint(p: Person): { team: string; season: number } | null {
  const all = p.sides.flatMap((s) => s.seasons)
  if (!all.length) return null
  const s = all.reduce((a, b) => (b.season > a.season ? b : a))
  return { team: s.team, season: s.season }
}

export function personLabel(p: Person): string {
  const s = lastStint(p)
  return s ? `${p.name} (last: ${s.team} ${s.season})` : p.name
}

export function sortedPeople(people: Person[]): Person[] {
  return [...people].sort((a, b) => a.name.localeCompare(b.name))
}

export function searchPeople(people: Person[], q: string): Person[] {
  const s = q.trim().toLowerCase()
  return s ? people.filter((p) => p.name.toLowerCase().includes(s)) : people
}

export type TrendRow = { label: string; season: number; team: string; rate: number | null; league: number | null; partial: boolean }

/** One row per stint for a metric: the unit's rate against that season's league rate. */
export function trendRows(seasons: Season[], league: Coaches['league'], side: 'off' | 'def', metric: string): TrendRow[] {
  return seasons.map((s) => ({
    label: `${s.season} ${s.team}`,
    season: s.season,
    team: s.team,
    rate: s.metrics[metric]?.rate ?? null,
    league: league[String(s.season)]?.[side]?.[metric] ?? s.metrics[metric]?.league ?? null,
    partial: s.partial,
  }))
}

export function consistencyText(c: string | null | undefined): string {
  return c ? c.charAt(0).toUpperCase() + c.slice(1) : 'Too early'
}
