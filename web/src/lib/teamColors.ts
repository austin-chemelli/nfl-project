/**
 * Team colors that work as chart marks. A team's brand color often doesn't: the Ravens' purple
 * disappears on a dark page, and four teams share one navy. So each team has a short list of brand
 * colors (`CHART`, from nflverse `teams_colors_logos`, most recognizable first), each color is fitted
 * to the page in both themes, and a matchup picks a pair the eye can tell apart. Hue is kept and only
 * lightness and chroma move, so a team stays recognizably itself. `teamColors.test.ts` checks all 992
 * matchups in both themes.
 */
import type { CSSProperties } from 'react'
import { canonicalTeam } from './teams'

export type TeamColor = { light: string; dark: string }

/** Black-and-something teams: a fitted black or silver can't separate from a mid-tone, so black on light, silver-white on dark. */
const INK: TeamColor = { light: '#2b2d30', dark: '#e4e7ea' }

const CHART: Record<string, (string | TeamColor)[]> = {
  ARI: ['#97233F', '#FFB612'], ATL: ['#A71930', '#A5ACAF'], BAL: ['#241773', '#9E7C0C'], BUF: ['#00338D', '#C60C30'],
  CAR: ['#0085CA', '#BFC0BF'], CHI: ['#E64100', '#0B162A'], CIN: ['#FB4F14', '#A5ACAF'], CLE: ['#FF3C00', '#311D00', '#A5ACAF'],
  DAL: ['#002244', '#B0B7BC'], DEN: ['#FB4F14', '#002244'], DET: ['#0076B6', '#B0B7BC'], GB: ['#203731', '#FFB612'],
  HOU: ['#03202F', '#A71930'], IND: ['#002C5F', '#A5ACAF'], JAX: ['#006778', '#D7A22A'], KC: ['#E31837', '#FFB612'],
  LA: ['#003594', '#FFD100'], LAC: ['#007BC7', '#FFC20E'], LV: ['#A5ACAF', INK], MIA: ['#008E97', '#F58220'],
  MIN: ['#4F2683', '#FFC62F'], NE: ['#002244', '#C60C30'], NO: ['#D3BC8D', INK], NYG: ['#0B2265', '#A71930'],
  NYJ: ['#003F2D', '#A5ACAF'], PHI: ['#004C54', '#A5ACAF'], PIT: ['#FFB612', '#C60C30'], SEA: ['#69BE28', '#002244'],
  SF: ['#AA0000', '#B3995D'], TB: ['#A71930', '#FF7900'], TEN: ['#4495D2', '#D50A0A'], WAS: ['#5A1414', '#FFB612'],
}
const UNKNOWN: (string | TeamColor)[] = ['#8A8984']

/** The chart surfaces in index.css (`--surface-1`); marks must clear 3:1 against them. */
export const SURFACE = { light: '#fcfcfd', dark: '#161b22' }
const MIN_CONTRAST = 3.2
/** Colors closer than this (OKLab × 100) read as the same team, to most readers and to red-green colorblind ones. */
export const MIN_DISTANCE = 18
export const MIN_CVD_DISTANCE = 8
/** Below this chroma a color is a neutral (silver, pewter) and stays one. Packers green sits just above it. */
const NEUTRAL = 0.02
/** One step of lightness: enough to split two same-tone colors while they stay the same color. */
const STEP = 0.14
const MIN_CHROMA = 0.11

type Lab = [number, number, number]

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const toSrgb = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055)
const rgbOf = (hex: string) => [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255))

const labOf = ([r, g, b]: number[]): Lab => {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s]
}

function linearOf([L, a, b]: Lab): number[] {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s]
}

const inGamut = (lab: Lab) => linearOf(lab).every((c) => c >= -0.0001 && c <= 1.0001)
const hexOf = (lab: Lab) => `#${linearOf(lab).map((c) => Math.round(255 * toSrgb(Math.min(1, Math.max(0, c)))).toString(16).padStart(2, '0')).join('')}`

const luminance = (hex: string) => {
  const [r, g, b] = rgbOf(hex)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const oklab = (hex: string) => labOf(rgbOf(hex))
const between = (a: Lab, b: Lab) => 100 * Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

export const distance = (x: string, y: string) => between(oklab(x), oklab(y))

/** Machado et al. (2009) at full severity: how protanopes and deuteranopes see a linear RGB color. */
const CVD = [
  [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
]
const simulate = (hex: string, m: number[][]): Lab => {
  const [r, g, b] = rgbOf(hex)
  return labOf(m.map((row) => Math.min(1, Math.max(0, row[0] * r + row[1] * g + row[2] * b))))
}

/** The distance a red-green colorblind reader sees, the worse of the two common types. */
export const cvdDistance = (x: string, y: string) => Math.min(...CVD.map((m) => between(simulate(x, m), simulate(y, m))))

/** One brand color for one theme: same hue, lightness moved only as far as the page needs, plus `shift` away from the surface. */
function fit(hex: string, mode: 'light' | 'dark', shift: number): string {
  const [L0, a, b] = oklab(hex)
  const C0 = Math.hypot(a, b)
  const h = Math.atan2(b, a)
  const C = C0 < NEUTRAL ? C0 : Math.max(C0, MIN_CHROMA)
  const at = (L: number): Lab => {
    let c = C
    while (c > 0 && !inGamut([L, c * Math.cos(h), c * Math.sin(h)])) c -= 0.004
    return [L, c * Math.cos(h), c * Math.sin(h)]
  }
  // walk toward the far end of the theme's range until the color clears the surface
  const step = mode === 'dark' ? 0.01 : -0.01
  let L = mode === 'dark' ? Math.max(L0, 0.6) : Math.min(Math.max(L0, 0.4), 0.66)
  while (contrast(hexOf(at(L)), SURFACE[mode]) < MIN_CONTRAST && L > 0.2 && L < 0.95) L += step
  return hexOf(at(Math.min(0.92, Math.max(0.22, L + Math.sign(step) * shift))))
}

const cache = new Map<string, TeamColor>()
function fitted(hex: string, shift = 0): TeamColor {
  const key = `${hex}${shift}`
  let c = cache.get(key)
  if (!c) cache.set(key, (c = { light: fit(hex, 'light', shift), dark: fit(hex, 'dark', shift) }))
  return c
}

/** A team's colors, least change first: the first brand color, the same color a step stronger, then the next brand color. */
const options = (team: string): TeamColor[] =>
  (CHART[canonicalTeam(team)] ?? UNKNOWN).flatMap((c) => (typeof c === 'string' ? [fitted(c), fitted(c, STEP)] : [c]))

/** How well a pair separates, 1 = exactly at the thresholds, taking the worse theme and the worse kind of vision. */
const score = (x: TeamColor, y: TeamColor) =>
  Math.min(...(['light', 'dark'] as const).flatMap((m) => [distance(x[m], y[m]) / MIN_DISTANCE, cvdDistance(x[m], y[m]) / MIN_CVD_DISTANCE]))

/** A team on its own (a slate card's accent, a list). */
export const teamColor = (team: string): TeamColor => options(team)[0]

/**
 * The pair for a matchup: the one that changes the teams least, the away team giving way first on a
 * tie. With no pair past the thresholds, the widest one wins.
 */
export function matchupColors(away: string, home: string): { away: TeamColor; home: TeamColor } {
  const pairs = options(home)
    .flatMap((h, i) => options(away).map((a, j) => ({ away: a, home: h, change: i + j, homeChange: i })))
    .sort((x, y) => x.change - y.change || x.homeChange - y.homeChange)
    .map(({ away: a, home: h }) => ({ away: a, home: h }))
  return pairs.find((p) => score(p.away, p.home) >= 1) ?? pairs.reduce((x, y) => (score(y.away, y.home) > score(x.away, x.home) ? y : x))
}

/** CSS variables for `[data-matchup]`; index.css picks the theme's pair as `--team-away` and `--team-home`. */
export function matchupVars(away: string, home: string): CSSProperties {
  const c = matchupColors(away, home)
  return { '--team-away-light': c.away.light, '--team-away-dark': c.away.dark, '--team-home-light': c.home.light, '--team-home-dark': c.home.dark } as CSSProperties
}
