import type { ScatterPoint, ScatterTone } from '../../charts/Scatter'
import type { TeamFeature, TeamRow, TeamsFile } from '../../data/contract'
import { dash, fmtUnit } from '../../lib/format'
import { teamDotVars } from '../../lib/teamColors'
import { DEFAULT_PRESET, PRESETS, presetFor, type Quadrants } from './presets'

export type ColorMode = 'team' | 'conference' | 'division' | 'none'

export function hasData(file: TeamsFile, id: string): boolean {
  return Object.values(file.teams).some((t) => t.values[id] != null)
}

export function featureById(file: TeamsFile, id: string): TeamFeature | undefined {
  return file.features.find((f) => f.id === id)
}

/** Features with a value for at least one team: the only ones the selectors offer. */
export function usableFeatures(file: TeamsFile): TeamFeature[] {
  return file.features.filter((f) => hasData(file, f.id))
}

/**
 * The axes to draw. Either id unknown, or without data in this file, falls back to preset 1; if the file
 * lacks preset 1 too, the first two usable features stand in. Null when there are fewer than two.
 */
export function resolveAxes(file: TeamsFile, x: string | null, y: string | null): { x: TeamFeature; y: TeamFeature } | null {
  const ok = (id: string | null) => (id && hasData(file, id) ? featureById(file, id) : undefined)
  const fx = ok(x)
  const fy = ok(y)
  if (fx && fy && fx.id !== fy.id) return { x: fx, y: fy } // one measure on both axes says nothing
  const d = [ok(DEFAULT_PRESET.x), ok(DEFAULT_PRESET.y)]
  if (d[0] && d[1]) return { x: d[0], y: d[1] }
  const use = usableFeatures(file)
  return use.length >= 2 ? { x: use[0], y: use[1] } : null
}

/** Presets whose two features both have data (a chip for anything else would open an empty chart). */
export function availablePresets(file: TeamsFile) {
  return PRESETS.filter((p) => hasData(file, p.x) && hasData(file, p.y))
}

/** Axis grouping for the selectors: feature groups in registry order. */
export function groupFeatures(features: TeamFeature[]): { name: string; features: TeamFeature[] }[] {
  const out: { name: string; features: TeamFeature[] }[] = []
  for (const f of features) {
    let g = out.find((o) => o.name === f.group_name)
    if (!g) out.push((g = { name: f.group_name, features: [] }))
    g.features.push(f)
  }
  return out
}

/** Right and top of an axis: better when the feature has a direction, otherwise higher. */
const hi = (f: TeamFeature) => (f.better ? 'better' : 'higher')
const lo = (f: TeamFeature) => (f.better ? 'worse' : 'lower')
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** A short label mid-sentence: "Luck" reads as "luck"; a name or initials (Elo, EPA trend) keep their capital. */
const mid = (short: string) => (/^(Elo\b|[A-Z]{2})/.test(short) ? short : short[0].toLowerCase() + short.slice(1))

/** Template captions for a pair no preset covers, in the order top left, top right, bottom left, bottom right. */
export function templateQuadrants(x: TeamFeature, y: TeamFeature): Quadrants {
  const q = (xw: string, yw: string) => `${cap(xw)} ${mid(x.short)}, ${yw} ${mid(y.short)}`
  return [q(lo(x), hi(y)), q(hi(x), hi(y)), q(lo(x), lo(y)), q(hi(x), lo(y))]
}

/** Preset captions where the pair is a preset, the template otherwise. */
export function quadrantsFor(x: TeamFeature, y: TeamFeature): Quadrants {
  return presetFor(x.id, y.id)?.quadrants ?? templateQuadrants(x, y)
}

export function ordinal(n: number): string {
  const m = n % 100
  if (m >= 11 && m <= 13) return `${n}th`
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'}`
}

const signed = (v: number, d: number) => {
  const r = Number(v.toFixed(d))
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(d)}`
}

/**
 * A value by its unit. Unlike the game page's `fmtUnit`: rates keep a decimal, so ranks can be read
 * off the table; differences of a rate read as percents, because "pts" elsewhere means win chance;
 * `_prior` features are gaps to the league average, so they carry a sign.
 */
export function fmtValue(v: number | null | undefined, f: TeamFeature): string {
  if (v == null || Number.isNaN(v)) return dash
  const gap = f.id.endsWith('_prior')
  switch (f.unit) {
    case 'pct': return gap ? `${signed(100 * v, 1)}%` : `${(100 * v).toFixed(1)}%`
    case 'pp': return `${signed(v, 1)}%`
    case 'prob_diff': return `${signed(100 * v, 1)}%`
    case 'count': return f.id.includes('turnover_margin') || f.id.endsWith('streak') ? signed(v, Number.isInteger(v) ? 0 : 1) : fmtUnit(v, f.unit)
    case 'seconds': return gap ? `${signed(v, 2)} s` : fmtUnit(v, f.unit)
    default: return fmtUnit(v, f.unit)
  }
}

/** "5th of 32", or null when the file has no rank for the team. */
export function rankText(t: TeamRow, f: TeamFeature): string | null {
  const r = t.rank?.[f.id]
  return r == null ? null : `${ordinal(r)} of ${f.n}`
}

export function recordText(t: TeamRow): string {
  return `${t.wins}–${t.losses}${t.ties ? `–${t.ties}` : ''}`
}

export function divisionsOf(file: TeamsFile): string[] {
  return [...new Set(Object.values(file.teams).map((t) => t.division))].sort()
}

export function colorMode(raw: string | null): ColorMode {
  return raw === 'conference' || raw === 'division' || raw === 'none' ? raw : 'team'
}

export function toneFor(t: TeamRow, mode: ColorMode, div: string | null): ScatterTone | undefined {
  if (mode === 'division' && div) return t.division === div ? 'strong' : 'muted'
  if (mode !== 'conference') return undefined
  return t.conference === 'NFC' ? 'conf-nfc' : 'conf-afc'
}

/** Team colors in Team mode and in Division mode, where the teams left out of a highlighted division go gray. */
const hasDot = (tone: ScatterTone | undefined, mode: ColorMode) => (mode === 'team' || mode === 'division') && tone !== 'muted'

/** Points for teams with a value on both axes, in alphabetical order, and the teams left out. */
export function buildPoints(file: TeamsFile, x: TeamFeature, y: TeamFeature, mode: ColorMode, div: string | null) {
  const points: ScatterPoint[] = []
  const missing: string[] = []
  for (const code of Object.keys(file.teams).sort()) {
    const t = file.teams[code]
    const vx = t.values[x.id]
    const vy = t.values[y.id]
    if (vx == null || vy == null) missing.push(code)
    else {
      const tone = toneFor(t, mode, div)
      points.push({ key: code, label: code, x: vx, y: vy, tone, dot: hasDot(tone, mode) ? teamDotVars(code) : undefined })
    }
  }
  return { points, missing }
}

/** Game result from a team's side: "W 27–21". Null until played. */
export function resultText(pf: number | null, pa: number | null): string | null {
  if (pf == null || pa == null) return null
  return `${pf > pa ? 'W' : pf < pa ? 'L' : 'T'} ${pf}–${pa}`
}
