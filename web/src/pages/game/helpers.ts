/** Pure helpers for the Game page (port of nfl.ui.game_helpers). */
import type { Contribution, Game, Meta, Tendency } from '../../data/contract'
import { fmtUnit } from '../../lib/format'
import { groupOf, helpFor, memberOf } from '../../lib/meta'
import { APPROACHES } from '../../lib/models'

export const QB_STATUS: Record<number, string> = { 0: 'healthy starter', 1: 'questionable / limited / new', 2: 'backup or unknown' }

export function ordinal(n: number): string {
  const r = Math.round(n)
  const v = r % 100
  if (v >= 11 && v <= 13) return `${r}th`
  return `${r}${({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[r % 10] ?? 'th'}`
}

/** Row order for the approach picker / dot strip. */
export const contribOrder = (contrib: Record<string, Contribution>) =>
  [...APPROACHES, 'ensemble'].filter((m) => m in contrib)

/** References, ensemble, then the four approaches (global is diagnostic, hidden). */
export function dotModels(models: Game['models']): string[] {
  return ['market_baseline', 'elo_v0', 'ensemble', ...APPROACHES].filter((m) => models[m]?.p_home != null)
}

// ------------------------------------------------------------------------------ contributions

export type ContribItem = { id: string; name: string; help: string; pp: number }

/** Home field first, then groups in registry order. */
export function contributionItems(cm: Contribution, meta: Meta): ContribItem[] {
  const order = meta.groups.groups.map((g) => g.id)
  const idx = (k: string) => (order.includes(k) ? order.indexOf(k) : 99)
  const items: ContribItem[] = [
    { id: 'home_field', name: 'Home field', help: 'The built-in edge the home team gets before anything else is considered.', pp: cm.home_field_pp ?? 0 },
  ]
  for (const k of Object.keys(cm.groups).sort((a, b) => idx(a) - idx(b))) {
    items.push({ id: k, name: groupOf(meta, k)?.name ?? k.replace(/_/g, ' '), help: helpFor(meta, k), pp: cm.groups[k].pp ?? 0 })
  }
  return items
}

/** Per-feature win-probability points inside a group, biggest first. */
export function featureContribRows(group: Contribution['groups'][string], meta: Meta) {
  return Object.entries(group.features)
    .filter((e): e is [string, number] => e[1] != null)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .map(([f, pp]) => ({ feature: f, label: featureLabel(meta, f), help: helpFor(meta, f), pp }))
}

export function featureLabel(meta: Meta, feature: string): string {
  return memberOf(meta, feature)?.label ?? feature.split('.').slice(1).join('.').replace(/_/g, ' ') ?? feature
}

// ---------------------------------------------------------------------------------------- edges

export function edgeRows(edges: Game['edges'], meta: Meta) {
  const rows = []
  const none: string[] = []
  for (const [id, e] of Object.entries(edges)) {
    const name = groupOf(meta, id)?.name ?? id
    if (!e.favors || e.strength_pct == null) {
      none.push(name)
      continue
    }
    rows.push({
      id, name, help: helpFor(meta, id), favors: e.favors, pct: e.strength_pct,
      sentence: `${e.favors}'s ${name} edge is in the ${ordinal(e.strength_pct)} percentile of matchups`,
    })
  }
  return { rows: rows.sort((a, b) => b.pct - a.pct), none }
}

// ------------------------------------------------------------------------------- tale of the tape

export type TapeRow = { feature: string; label: string; help: string; home: string; away: string }
export type TapeGroup = { id: string; name: string; help: string; rows: TapeRow[] }

/** heading -> groups -> formatted rows, registry order; features with no values are skipped. */
export function tape(features: Game['features'], meta: Meta): { heading: string; groups: TapeGroup[] }[] {
  const byGroup = new Map<string, TapeRow[]>()
  for (const [f, d] of Object.entries(features)) {
    const { home, away, game } = d
    if (home == null && away == null && game == null) continue
    const unit = memberOf(meta, f)?.unit
    const gid = d.group ?? memberOf(meta, f)?.group ?? 'other'
    const rows = byGroup.get(gid) ?? []
    rows.push({
      feature: f, label: featureLabel(meta, f), help: helpFor(meta, f),
      home: fmtUnit(home ?? game, unit), away: fmtUnit(away ?? game, unit),
    })
    byGroup.set(gid, rows)
  }
  const out = new Map<string, TapeGroup[]>()
  const seen = new Set<string>()
  for (const g of meta.groups.groups) {
    const rows = byGroup.get(g.id)
    if (!rows) continue
    out.set(g.heading, [...(out.get(g.heading) ?? []), { id: g.id, name: g.name, help: g.description, rows }])
    seen.add(g.id)
  }
  for (const [id, rows] of byGroup) {
    if (!seen.has(id)) out.set('Other', [...(out.get('Other') ?? []), { id, name: id.replace(/_/g, ' '), help: '', rows }])
  }
  return [...out].map(([heading, groups]) => ({ heading, groups }))
}

// ------------------------------------------------------------------------------------ tendencies

export type TendRow = { key: string; label: string; help: string; unit: string; a: number | null; b: number | null; league: number | null; n: number }
export type TendBlock = { key: string; title: string; note: string; aName: string; bName: string; aColor: string; bColor: string; rows: TendRow[] }

const AWAY_COLOR = 'var(--div-neg)'
const HOME_COLOR = 'var(--div-pos)'

const find = (rows: Tendency[], team_side: string, side: string, metric: string, situation: string) =>
  rows.find((r) => r.team_side === team_side && r.side === side && r.metric === metric && r.situation === situation)

/**
 * Dumbbell blocks for one situation. Metrics that have a `pair` in meta (offense metric with its
 * defensive counterpart) become matchup blocks: team A's offense vs team B's defense, one block per
 * direction. Unpaired metrics have no counterpart, so they compare the two teams directly: one
 * block of offensive habits, one of defensive habits.
 */
export function tendencyBlocks(tend: Tendency[], meta: Meta, situation: string, home: string, away: string): TendBlock[] {
  const metrics = Object.entries(meta.tendency_metrics)
  const row = (id: string, a: Tendency | undefined, b: Tendency | undefined): TendRow | null => {
    if (!a && !b) return null
    const m = meta.tendency_metrics[id]
    return {
      key: id, label: m.label, help: m.help, unit: m.unit, a: a?.rate ?? null, b: b?.rate ?? null,
      league: (a ?? b)?.league_rate ?? null, n: Math.min(a?.n ?? Infinity, b?.n ?? Infinity),
    }
  }
  const nn = (rs: (TendRow | null)[]) => rs.filter((r): r is TendRow => r != null && (r.a != null || r.b != null))
  const blocks: TendBlock[] = []
  for (const [offTeam, offSide, defTeam, defSide] of [[away, 'away', home, 'home'], [home, 'home', away, 'away']] as const) {
    const rows = nn(
      metrics
        .filter(([, m]) => m.side === 'off' && m.pair)
        .map(([id, m]) => {
          const r = row(id, find(tend, offSide, 'off', id, situation), find(tend, defSide, 'def', m.pair as string, situation))
          return r && { ...r, help: `${m.help} Defense counterpart: ${meta.tendency_metrics[m.pair as string]?.label ?? m.pair}.` }
        }),
    )
    blocks.push({
      key: `${offSide}-off`, title: `${offTeam} offense vs ${defTeam} defense`,
      note: `Dot per side: ${offTeam}'s offense on the metric and ${defTeam}'s defense on its counterpart (what it allows or faces). Far apart means a mismatch.`,
      aName: `${offTeam} offense`, bName: `${defTeam} defense`,
      aColor: offSide === 'away' ? AWAY_COLOR : HOME_COLOR, bColor: offSide === 'away' ? HOME_COLOR : AWAY_COLOR, rows,
    })
  }
  for (const side of ['off', 'def'] as const) {
    const rows = nn(
      metrics.filter(([, m]) => m.side === side && !m.pair).map(([id]) => row(id, find(tend, 'away', side, id, situation), find(tend, 'home', side, id, situation))),
    )
    blocks.push({
      key: `habits-${side}`, title: side === 'off' ? 'Offensive habits' : 'Defensive habits',
      note: 'These metrics have no counterpart on the other side, so the two teams are compared directly.',
      aName: away, bName: home, aColor: AWAY_COLOR, bColor: HOME_COLOR, rows,
    })
  }
  return blocks.filter((b) => b.rows.length > 0)
}

/** Split a block's rows by unit so each chart shares one sensible scale. */
export function byUnit(rows: TendRow[]): { unit: string; rows: TendRow[]; domain: [number, number] }[] {
  const units = [...new Set(rows.map((r) => r.unit))]
  return units.map((unit) => {
    const rs = rows.filter((r) => r.unit === unit)
    const vals = rs.flatMap((r) => [r.a, r.b, r.league]).filter((v): v is number => v != null)
    const lo = Math.min(...vals)
    const hi = Math.max(...vals)
    const pad = Math.max((hi - lo) * 0.15, unit === 'pct' ? 0.02 : 0.03)
    return { unit, rows: rs, domain: [lo - pad, hi + pad] as [number, number] }
  })
}

// ------------------------------------------------------------------------------------- injuries

export function injuryRank(status: string): number {
  const s = status.toLowerCase()
  if (/\b(out|ir|pup|nfi|susp)/.test(s)) return 0
  if (s.includes('doubtful')) return 1
  if (s.includes('questionable')) return 2
  return 3
}

export const sortInjuries = <T extends { status: string; player: string }>(rows: T[]): T[] =>
  [...rows].sort((a, b) => injuryRank(a.status) - injuryRank(b.status) || a.player.localeCompare(b.player))

// ------------------------------------------------------------------------------------ narrative

/** Words plus arrows (never color alone): sized by |impact|, direction by sign. */
export function impactMarker(impact: number | null | undefined): { arrows: string; words: string } {
  const i = Math.round(impact ?? 0)
  if (i === 0) return { arrows: '●', words: 'neutral' }
  return { arrows: (i > 0 ? '▲' : '▼').repeat(Math.min(Math.abs(i), 2)), words: `${i > 0 ? 'helps' : 'hurts'}${Math.abs(i) >= 2 ? ' a lot' : ''}` }
}

export const trendStatus = (working: boolean | null): string => (working == null ? 'unclear' : working ? 'working' : 'not working')

export const sortNotes = <T extends { impact: number }>(notes: T[]): T[] => [...notes].sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))

export const sortMatchupNotes = <T extends { support: number }>(notes: T[]): T[] => [...notes].sort((a, b) => b.support - a.support)

export function sourcesText(n: number): string {
  return `${n} source${n === 1 ? '' : 's'}`
}
