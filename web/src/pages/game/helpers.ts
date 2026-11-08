/** Pure helpers for the Game page (port of nfl.ui.game_helpers). */
import type { DriveTip } from '../../charts'
import type { Contribution, Drive, Game, Meta, RetroGame, Tendency, WpPlay, WpSeries } from '../../data/contract'
import { fmtUnit, kickoffEt, pct } from '../../lib/format'
import { countsAsEdge, edgePct, groupOf, helpFor, isContextOnly, memberOf } from '../../lib/meta'
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
  APPROACHES.filter((m) => m in contrib)

/** References, then the four approaches (global is diagnostic, hidden). */
export function dotModels(models: Game['models']): string[] {
  return ['market_baseline', 'elo_v0', ...APPROACHES].filter((m) => models[m]?.p_home != null)
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

// -------------------------------------------------------------------------------------- preview

export type PreviewRow = { id: string; name: string; help: string; edge: string; pct: number | null; pp: number | null; overlay: number | null }

/** "JAX, 90th pct"; a matchup in the bottom tenth of all edges reads as even, whichever way it leans. */
function edgeLabel(e: Game['edges'][string] | undefined): string {
  if (!e) return ''
  return !e.favors || e.strength_pct == null || e.strength_pct < 10 ? 'about even' : `${e.favors}, ${ordinal(edgePct(e.strength_pct))} pct`
}

/**
 * Home field, then the groups in registry order. `pp` is the Global fit (what history says the edge
 * is worth); `overlay` is the chosen approach on the same row. A group neither side has is no row,
 * so `meta.groups` decides what appears: new groups show up and zeroed ones go with no change here.
 */
export function previewRows(g: Game, meta: Meta, approach: string | null): PreviewRow[] {
  const base = g.contributions.global
  const over = approach ? g.contributions[approach] : undefined
  if (!base) return []
  // The fit's home bonus is a constant, and the neutral-site discount sits in Venue & weather. Read
  // apart, a neutral game shows a full home edge; so that discount moves onto the home field row.
  const discount = (c: Contribution | undefined) => (g.neutral_site ? (c?.groups.venue_weather?.features['environment.neutral_site'] ?? 0) : 0)
  const homeField = (c: Contribution | undefined) => (c?.home_field_pp == null ? null : c.home_field_pp + discount(c))
  const rows: PreviewRow[] = [{
    id: 'home_field', name: 'Home field',
    help: g.neutral_site ? 'A neutral site: the usual home edge after the neutral-site discount, as each reading prices it.' : 'The built-in edge the home team gets before anything else is considered.',
    edge: g.neutral_site ? 'neutral site' : `${g.home} at home`, pct: null, pp: homeField(base) ?? 0, overlay: homeField(over),
  }]
  for (const { id, name } of meta.groups.groups) {
    if (isContextOnly(meta, id)) continue
    const venue = id === 'venue_weather'
    const pp = base.groups[id]?.pp == null ? null : (base.groups[id].pp as number) - (venue ? discount(base) : 0)
    const overlay = over?.groups[id]?.pp == null ? null : (over.groups[id].pp as number) - (venue ? discount(over) : 0)
    if (pp == null && !overlay) continue
    const edge = countsAsEdge(meta, id, g.neutral_site) ? g.edges[id] : undefined
    rows.push({ id, name, help: helpFor(meta, id), edge: edgeLabel(edge), pct: edge?.strength_pct ?? null, pp, overlay })
  }
  return rows
}

/** "Followed a 12.5-point line move toward JAX": the Sharp's market read, in raw points; null when the line barely moved. */
export function lineMoveChip(g: Game): string | null {
  const v = g.features['market.line_move_pts']?.game
  if (v == null || Math.abs(v) < 1) return null
  const n = Math.abs(v)
  const article = /^(8|11|18)(\.|$)/.test(String(n)) ? 'an' : 'a'
  return `Followed ${article} ${n}-point line move toward ${v > 0 ? g.home : g.away}`
}

export type LiveReading = { feature: string; label: string; help: string; game: string | null; away: string | null; home: string | null }
export type LiveGroup = { id: string; name: string; help: string; readings: LiveReading[] }

/**
 * The groups history can't price (Market behavior, Buzz: live only, so the all-history fit has no
 * bar for them), as their raw readings for this game. Any group an approach weighs that the fit
 * left out lands here, so a new live-only group shows up with no change. A reading nobody took is
 * null; a group with no readings at all still appears, saying so.
 */
export function liveOnlyGroups(g: Game, meta: Meta): LiveGroup[] {
  const base = g.contributions.global
  if (!base) return []
  const out: LiveGroup[] = []
  for (const grp of meta.groups.groups) {
    if (isContextOnly(meta, grp.id) || base.groups[grp.id]?.pp != null) continue
    const readings = grp.members.map((m) => {
      const v = g.features[m.feature]
      const val = (x: number | null | undefined) => (x == null ? null : fmtUnit(x, m.unit).replace(/^-/, '−'))
      let game: string | null = null
      if (v?.game != null) {
        // game-level readings lean toward a side: a line move in points, a share of bets on the home team
        if (m.unit === 'points') game = Math.abs(v.game) < 0.05 ? 'no move' : `${Math.abs(v.game).toFixed(1)} pts toward ${v.game > 0 ? g.home : g.away}`
        else if (m.unit === 'pct' && m.feature.endsWith('_home')) game = `${pct(v.game)} on ${g.home}`
        else game = val(v.game)
      }
      return { feature: m.feature, label: m.label, help: helpFor(meta, m.feature), game, away: val(v?.away), home: val(v?.home) }
    })
    out.push({ id: grp.id, name: grp.name, help: helpFor(meta, grp.id), readings })
  }
  return out
}

/** Show the live-only readings once the week's narrative pass has filled at least one (Austin,
 * 2026-11-07): before that the table is a column of "no reading yet" beside a line-move reading the
 * line section already covers. */
export function liveReady(groups: LiveGroup[]): boolean {
  return groups.some((grp) => grp.readings.some((r) => r.feature.startsWith('narrative.') && (r.game != null || r.away != null || r.home != null)))
}

// -------------------------------------------------------------------------------------- retro

export type SwingRow = { key: string; label: string; value: number; teams: { team: string; swing: number; sentence: string }[] }

/**
 * The swing factors with both teams on one bar, so the opponent's missed kick reads as your gain:
 * value = home's swing minus away's, toward home when positive. Split as the record flags them:
 * variance also reflects how a team played, pure luck doesn't. Factors nobody moved are left out.
 */
export function swingRows(r: RetroGame): { variance: SwingRow[]; pure: SwingRow[]; net: number } {
  const { home, away } = r.teams
  const rows = home.luck.flatMap((h) => {
    const a = away.luck.find((x) => x.factor === h.factor)
    const swing = a?.swing_pts ?? 0
    if (h.swing_pts === 0 && swing === 0) return []
    const row: SwingRow = {
      key: h.factor, label: h.label, value: Math.round((h.swing_pts - swing) * 10) / 10,
      teams: [{ team: away.team, swing, sentence: a?.sentence ?? '' }, { team: home.team, swing: h.swing_pts, sentence: h.sentence }],
    }
    return [{ row, skill: h.partly_skill }]
  })
  return {
    variance: rows.filter((x) => x.skill).map((x) => x.row),
    pure: rows.filter((x) => !x.skill).map((x) => x.row),
    net: Math.round((home.luck_net - away.luck_net) * 10) / 10,
  }
}

/** "GB won 5 of 8 phases" over the ones with a winner; a tie between the teams says so. */
export function phaseSummary(r: RetroGame): string {
  const home = r.phases.filter((p) => p.leader === 'home').length
  const away = r.phases.filter((p) => p.leader === 'away').length
  if (home === away) return `${r.away} and ${r.home} split the phases ${home}–${away}`
  return `${home > away ? r.home : r.away} won ${Math.max(home, away)} of ${r.phases.length} phases`
}

/** The played-like verdict step by step, in win chances; null on a retro from before schema 3. */
export function playedLikeSteps(r: RetroGame) {
  const { home_epa: h, away_epa: a, home_success: hs, away_success: as, p_base: base, p_home: p } = r.played_like
  if (h == null || a == null || hs == null || as == null || base == null) return null
  const leader = h >= a ? r.home : r.away
  const gap = Math.abs(h - a)
  return {
    homeEpa: fmtUnit(h, 'epa'), awayEpa: fmtUnit(a, 'epa'), homeSuccess: pct(hs), awaySuccess: pct(as),
    sentence: `Before any plays, the home side wins ${pct(base)} of the time. ${leader}'s edge of ${gap.toFixed(3)} EPA a play moves ${r.home} to ${pct(p)}.`,
  }
}

// ---------------------------------------------------------------------------------------- edges

export function edgeRows(edges: Game['edges'], meta: Meta, neutral = false) {
  const rows = []
  const none: string[] = []
  for (const [id, e] of Object.entries(edges)) {
    if (!countsAsEdge(meta, id, neutral)) continue
    const name = groupOf(meta, id)?.name ?? id
    if (!e.favors || e.strength_pct == null) {
      none.push(name)
      continue
    }
    rows.push({
      id, name, help: helpFor(meta, id), favors: e.favors, pct: e.strength_pct,
      sentence: `${e.favors}'s ${name} edge is bigger than ${edgePct(e.strength_pct)}% of matchups`,
    })
  }
  return { rows: rows.sort((a, b) => b.pct - a.pct), none }
}

// ------------------------------------------------------------------------------- tale of the tape

/** `band` is set only when the row can be drawn on the league's range: a team feature with two values and a real spread. */
export type TapeBand = { lo: number; q1: number; med: number; q3: number; hi: number; homeV: number; awayV: number; stands: boolean; flip: boolean }
export type TapeRow = { feature: string; label: string; help: string; home: string; away: string; unit: string | undefined; band: TapeBand | null }
export type TapeGroup = { id: string; name: string; help: string; rows: TapeRow[] }

/** The two teams on the league's band; `stands` when their gap is wider than the league's middle half. */
function tapeBand(f: string, d: Game['features'][string], meta: Meta): TapeBand | null {
  const b = meta.feature_bands[f]
  const m = memberOf(meta, f)
  const unit = m?.unit
  const { home, away } = d
  if (!b || home == null || away == null || unit === 'flag' || !(b.q3 > b.q1) || !(b.hi > b.lo)) return null
  return { ...b, homeV: home, awayV: away, stands: Math.abs(home - away) > b.q3 - b.q1, flip: (m?.sign ?? 1) < 0 }
}

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
      home: fmtUnit(home ?? game, unit), away: fmtUnit(away ?? game, unit), unit, band: tapeBand(f, d, meta),
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

const AWAY_COLOR = 'var(--team-away)'
const HOME_COLOR = 'var(--team-home)'

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

export const trendStatus = (working: boolean | null): string => (working == null ? 'results unclear' : working ? 'producing results' : 'not producing results')

export const sortNotes = <T extends { impact: number }>(notes: T[]): T[] => [...notes].sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))

export const sortMatchupNotes = <T extends { support: number }>(notes: T[]): T[] => [...notes].sort((a, b) => b.support - a.support)

export function sourcesText(n: number): string {
  return `${n} source${n === 1 ? '' : 's'}`
}

/**
 * "Market line: The Odds API, Sun 1:00 PM ET." Null with no line or no source. A schedule line's
 * as_of is the synthetic kickoff − 2h stamp, not when it was seen, so only a snapshot prints a time.
 */
export function marketSource(market: { p_home?: number | null; source?: string | null; as_of?: string | null } | null | undefined): string | null {
  if (market?.p_home == null || !market.source) return null
  if (market.source === 'schedules') return 'Market line: the nflverse schedule (no time recorded).'
  const name = market.source === 'odds_api' ? 'The Odds API' : market.source
  return market.as_of ? `Market line: ${name}, ${kickoffEt(market.as_of)}.` : `Market line: ${name}.`
}

// ------------------------------------------------------------------------- win probability (M15.3)

/** Plays in the order they happened: the chart's marks and the list under it share this order. */
export const orderedPlays = (ws: WpSeries): WpPlay[] => [...ws.plays].sort((a, b) => a.t - b.t)

const pc = (p: number) => `${Math.round(100 * p)}%`
const score = (r: RetroGame) => `${Math.max(r.result.home_score, r.result.away_score)}–${Math.min(r.result.home_score, r.result.away_score)}`
/** Period from elapsed seconds: Q1 to Q4, then overtime. */
const periodAt = (t: number) => (t >= 3600 ? 'overtime' : `Q${Math.floor(t / 900) + 1}`)

/** The one sentence over the win-probability chart; null when the record has no series. */
export function wpLede(r: RetroGame): string | null {
  const ws = r.wp_series
  if (!ws) return null
  const m = r.result.margin
  if (m === 0) return `Tied ${r.result.home_score}–${r.result.away_score}${ws.ot ? ' after overtime' : ''}.`
  const home = m > 0
  const winner = home ? r.home : r.away
  const low = ws.winner_low ?? [0, Math.min(...ws.points.map(([, p]) => (home ? p : 1 - p)))]
  // a low at t = 0 is where the winner started, so it never "fell" there
  if (ws.winner_low && low[0] > 0 && low[1] < 0.25) {
    const pctText = low[1] < 0.005 ? 'under 1%' : pc(low[1])
    const when = periodAt(low[0])
    return `${winner} won ${score(r)} after its win chance fell to ${pctText} ${when === 'overtime' ? 'in overtime' : `in ${when}`}.`
  }
  return `${winner}'s win chance never fell below ${Math.floor(low[1] * 100 + 1e-9)}% on the way to a ${score(r)} win.`
}

const whereOnField = (yl: number) => (yl === 50 ? 'midfield' : yl < 50 ? `own ${yl}` : `opponent's ${100 - yl}`)
const DRIVE_RESULTS: Record<string, string> = { 'Opp touchdown': 'Touchdown for the defense', 'End of half': 'Ran out of time' }

/** A drive's hover card and row label: when, how it ended, plays and time, where it went. */
export function driveText(d: Drive): DriveTip {
  const secs = Math.max(0, d.t1 - d.t0)
  const time = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`
  const plays = d.plays == null ? null : `${d.plays} ${d.plays === 1 ? 'play' : 'plays'}`
  const end = d.result === 'Touchdown' ? 'the end zone' : d.end_yl == null ? null : whereOnField(d.end_yl)
  return {
    title: `${d.qtr >= 5 ? 'OT' : `Q${d.qtr}`} · ${d.team}`,
    result: d.result == null ? 'Result not recorded' : (DRIVE_RESULTS[d.result] ?? d.result),
    span: plays ? `${plays}, ${time}` : time,
    detail: d.start_yl == null ? null : end ? `From ${whereOnField(d.start_yl)} to ${end}` : `From ${whereOnField(d.start_yl)}`,
  }
}

/** One sentence over the drives: how often each team scored, the away team first. */
export function driveLede(r: RetroGame): string | null {
  const ds = r.drives
  if (!ds?.length) return null
  const line = (team: string) => {
    const own = ds.filter((d) => d.team === team)
    return { team, scored: own.filter((d) => d.result === 'Touchdown' || d.result === 'Field goal').length, n: own.length }
  }
  const a = line(r.away)
  const h = line(r.home)
  return `${a.team} scored on ${a.scored} of ${a.n} drives, ${h.team} on ${h.scored} of ${h.n}.`
}

const FACTOR_LABELS: Record<string, string> = {
  fumbles: 'Fumble recoveries',
  interceptions: 'Interceptions thrown',
  third_down: '3rd-down conversions',
  fourth_down: '4th-down conversions',
  kicking: 'Field goals and extra points',
  penalties: 'Penalty yards',
  special_teams: 'Return TDs and blocked kicks',
}

/** A luck factor's label from the retro record, with a static fallback. */
export function factorLabel(r: RetroGame, factor: string): string {
  return [...r.teams.home.luck, ...r.teams.away.luck].find((l) => l.factor === factor)?.label ?? FACTOR_LABELS[factor] ?? factor.replace(/_/g, ' ')
}

export type MarkText = { title: string; helped: 'home' | 'away'; team: string; prob: string; swing: string; text: string; counted: string | null }

/**
 * One turning point as strings. The numbers are the team it helped (wpa > 0 helps home): its win
 * probability before and after, and the swing in points. `factor` is the label to print, if any.
 */
export function markText(p: WpPlay, home: string, away: string, factor?: string | null): MarkText {
  const helped = p.wpa > 0 ? 'home' : 'away'
  const view = (x: number) => (helped === 'home' ? x : 1 - x)
  const when = p.qtr >= 5 ? `OT ${p.clock}` : `Q${p.qtr} ${p.clock}`
  return {
    title: p.team ? `${when} · ${p.team}` : when,
    helped,
    team: helped === 'home' ? home : away,
    prob: `${pc(view(p.p_before))} → ${pc(view(p.p_after))}`,
    // from the rounded ends, so the row's own arithmetic holds: 53% → 73% is +20, not +19
    swing: `+${Math.abs(Math.round(100 * view(p.p_after)) - Math.round(100 * view(p.p_before)))} pts`,
    text: p.text.replace(/^\(\d*:\d\d\)\s*/, ''), // the title already has the clock
    counted: factor ? `Counted in: ${factor}` : null,
  }
}
