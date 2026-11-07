/** Reads a tendency row (ADR 0022): is this team doing what its play-caller's past and its own last season suggested? */
import type { TeamChange, TeamFile, TeamMetric, TeamUnit } from '../../data/contract'

/**
 * `rough`: the study says this guess is little better than the league middle, so no verdict. `no_range`: no
 * measured miss to judge by. `mixed`: a caller changed during the season, so the rates aren't his alone.
 */
export type Verdict = 'as_expected' | 'more' | 'less' | 'rough' | 'no_range' | 'waiting' | 'mixed'

/** Keeps a value exactly on the edge of the range inside it, past float error. */
const EDGE = 1e-9
/**
 * The range is the typical miss, so about half of all rows land outside it. A row has to be this many misses
 * from expected to be called out in the tile or the line above a chart.
 */
export const NOTABLE = 1.5

export function verdict(row: TeamMetric, mixed = false): Verdict {
  const { expected: e, observed: o } = row
  if (!e || e.miss == null) return 'no_range'
  if (e.strength === 'weak') return 'rough'
  if (!o) return 'waiting'
  if (mixed) return 'mixed'
  if (Math.abs(o.pct - e.pct) <= e.miss + EDGE) return 'as_expected'
  return o.pct > e.pct ? 'more' : 'less'
}

/** How far outside its typical miss a row is: 1 is on the edge of the range. Rows with no verdict score 0. */
export const distance = (row: TeamMetric, mixed = false): number => {
  const v = verdict(row, mixed)
  if (v !== 'as_expected' && v !== 'more' && v !== 'less') return 0
  return Math.abs(row.observed!.pct - row.expected!.pct) / row.expected!.miss!
}

const tier = (row: TeamMetric, mixed: boolean): number => {
  const v = verdict(row, mixed)
  return v === 'more' || v === 'less' ? 0 : v === 'as_expected' || v === 'waiting' || v === 'mixed' ? 1 : v === 'rough' ? 2 : 3
}

/** Furthest from expected first, then what's on course, then rough guesses, then rows with no range. */
export function sortRows(rows: TeamMetric[], mixed = false): TeamMetric[] {
  return [...rows].sort((a, b) => tier(a, mixed) - tier(b, mixed) || distance(b, mixed) - distance(a, mixed) || a.label.localeCompare(b.label))
}

export const VERDICT_TEXT: Record<Verdict, string> = {
  as_expected: 'As expected',
  more: 'More than expected',
  less: 'Less than expected',
  rough: 'Rough guess',
  no_range: 'No measured range',
  waiting: 'Prediction',
  mixed: 'Two callers',
}

/** The latest play-calling change on a side this season, if there was one. */
export function callerChange(file: TeamFile, side: 'off' | 'def'): TeamChange | null {
  const role = side === 'off' ? 'OFF_PC' : 'DEF_PC'
  return file.staff.changes.filter((c) => c.role === role).at(-1) ?? null
}

/** Why a unit's rates aren't its current caller's alone. */
export function changeLine(c: TeamChange, through: number | null): string {
  if (through != null && c.start_week > through) return `${c.name} took over in Week ${c.start_week}, so these games were called by someone else.`
  const weeks = c.start_week === 2 ? 'Week 1' : `Weeks 1–${c.start_week - 1}`
  return c.replaced ? `${weeks} ${c.start_week === 2 ? 'was' : 'were'} called by ${c.replaced}, so these rates mix two callers.` : `${c.name} took over in Week ${c.start_week}, so these rates mix two callers.`
}

/** The row furthest from expected across both units, for the tile. Null when nothing is well outside its range, or a unit changed callers. */
export function furthest(file: TeamFile): { row: TeamMetric; side: 'off' | 'def' } | null {
  let best: { row: TeamMetric; side: 'off' | 'def' } | null = null
  for (const side of ['off', 'def'] as const) {
    if (callerChange(file, side)) continue
    for (const row of file.units[side].live) {
      if (distance(row) < NOTABLE || (verdict(row) !== 'more' && verdict(row) !== 'less')) continue
      if (best == null || distance(row) > distance(best.row)) best = { row, side }
    }
  }
  return best
}

/** Where a row's expected value came from, in words. */
export function basis(row: TeamMetric, file: TeamFile, caller: string | null): string {
  const e = row.expected
  if (!e) return ''
  const last = row.team_last ? `${file.team}'s ${row.team_last.season}` : null
  if (e.weight_on_caller === 0 || !caller || row.caller_seasons === 0) return last ? `From ${last} alone` : ''
  const seasons = `${row.caller_seasons} season${row.caller_seasons === 1 ? '' : 's'} of ${caller}'s past`
  return e.weight_on_caller === 1 || !last ? `From ${seasons}` : `From ${seasons} and ${last}`
}

/** One line about the unit: its furthest row, naming only the sources that row's expected value used. */
export function unitLine(unit: TeamUnit): string | null {
  const name = unit.caller?.confirmed ? unit.caller.name : null
  const top = sortRows(unit.live)[0]
  if (!top?.expected || distance(top) < NOTABLE) return null
  const v = verdict(top)
  if (v !== 'more' && v !== 'less') return null
  const w = top.expected.weight_on_caller
  const source = !name || w === 0 ? 'last season' : w === 1 ? `${name}'s past` : `${name}'s past and last season`
  return `${top.label} is running ${v === 'more' ? 'above' : 'below'} what ${source} suggested.`
}

export function fmtRate(v: number, unit: string): string {
  if (unit === 'seconds') return `${v.toFixed(2)} s`
  if (unit === 'epa') return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
  return `${(100 * v).toFixed(1)}%`
}

/** A prediction in words: with misses this size, a percentage would claim too much. */
export function expectWords(row: TeamMetric): [string, string] {
  const p = row.expected?.pct
  if (p == null) return ['–', '']
  if (p >= 2 / 3) return [cap(row.hi), 'than most']
  if (p <= 1 / 3) return [cap(row.lo), 'than most']
  return ['About', 'average']
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** "Weeks 2–6" from a sorted list of weeks, runs joined. */
export function weekList(weeks: number[]): string {
  const runs: [number, number][] = []
  for (const w of [...weeks].sort((a, b) => a - b)) {
    const last = runs.at(-1)
    if (last && w === last[1] + 1) last[1] = w
    else runs.push([w, w])
  }
  const text = runs.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(', ')
  return `Week${weeks.length > 1 ? 's' : ''} ${text}`
}

/** Who started when the Week 1 starter didn't: one line per quarterback. */
export function starterLines(file: TeamFile): string[] {
  const by = new Map<string, number[]>()
  for (const s of file.other_starter_weeks) by.set(s.qb, [...(by.get(s.qb) ?? []), s.week])
  return [...by].map(([qb, weeks]) => `${qb} started ${weekList(weeks)}.`)
}

