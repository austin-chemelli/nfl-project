/**
 * Reads a tendency row (ADR 0022, revised 2026-11-07): which past does this season look like, the play-caller's
 * own or the team's last season? No blended "expected" value: the two inputs are shown as they are.
 */
import type { TeamChange, TeamFile, TeamMetric, TeamUnit } from '../../data/contract'

/** Within this share of the league (about five places of 32), two values look alike. */
export const NEAR = 0.15

export type Read = 'both' | 'past' | 'last' | 'neither' | 'steady' | 'changed'

export function read(row: TeamMetric): Read | null {
  const o = row.observed?.pct
  if (o == null) return null
  const past = row.caller_past?.pct
  const last = row.team_last?.pct
  const nearPast = past != null && Math.abs(o - past) <= NEAR
  const nearLast = last != null && Math.abs(o - last) <= NEAR
  if (past != null && last != null) return nearPast && nearLast ? 'both' : nearPast ? 'past' : nearLast ? 'last' : 'neither'
  if (last != null) return nearLast ? 'steady' : 'changed'
  if (past != null) return nearPast ? 'past' : 'neither'
  return null
}

export const READ_TEXT: Record<Read, string> = {
  both: 'Matches both',
  past: 'Matches caller',
  last: 'Matches last year',
  neither: 'New this year',
  steady: 'Same as last year',
  changed: 'Changed',
}

/** For a measure with no season yet: which mark past cases say to watch. */
export function leanText(row: TeamMetric): string | null {
  if (row.lean === 'caller') return 'Watch the caller'
  if (row.lean === 'team') return 'Watch last year'
  if (row.lean === 'both') return 'Between the two'
  return null
}

const ORDER: Record<Read, number> = { neither: 0, changed: 1, past: 2, last: 3, both: 4, steady: 5 }

/** What's new first, then what follows the caller, then what follows the team. */
export function sortRows(rows: TeamMetric[]): TeamMetric[] {
  const key = (m: TeamMetric) => {
    const r = read(m)
    return r ? ORDER[r] : 9
  }
  return [...rows].sort((a, b) => key(a) - key(b) || a.label.localeCompare(b.label))
}

/** One line per unit: how much of this season looks like the caller's past and how much like last year. */
export function unitLine(unit: TeamUnit, team: string): string | null {
  const reads = unit.live.map(read).filter((r): r is Read => r != null)
  if (reads.length === 0) return null
  const n = reads.length
  const last = reads.filter((r) => r === 'last' || r === 'both' || r === 'steady').length
  const name = unit.caller?.confirmed ? unit.caller.name : null
  const hasPast = unit.live.some((m) => m.caller_past != null)
  if (name && hasPast) {
    const past = reads.filter((r) => r === 'past' || r === 'both').length
    return `Looks like ${name}'s past on ${past} of ${n} measures, and like last year's ${team} on ${last}.`
  }
  return `${name ? `${name} has no past as a play-caller in our data, so the` : 'The'} comparison is last year's ${team}: ${last} of ${n} measures look the same.`
}

/** The latest play-calling change on a side this season, if there was one. */
export function callerChange(file: TeamFile, side: 'off' | 'def'): TeamChange | null {
  const role = side === 'off' ? 'OFF_PC' : 'DEF_PC'
  return file.staff.changes.filter((c) => c.role === role).at(-1) ?? null
}

/** Why a unit's numbers aren't its current caller's alone. */
export function changeLine(c: TeamChange, through: number | null): string {
  if (through != null && c.start_week > through) return `${c.name} took over in Week ${c.start_week}, so these games were called by someone else.`
  const weeks = c.start_week === 2 ? 'Week 1 was' : `Weeks 1–${c.start_week - 1} were`
  return c.replaced ? `${weeks} called by ${c.replaced}, so these numbers mix two callers.` : `${c.name} took over in Week ${c.start_week}, so these numbers mix two callers.`
}

/** A move this big from last season is worth a tile: about ten places of 32. */
export const BIG_CHANGE = 0.3

/** The measure that moved most from last season, across both units. */
export function biggestChange(file: TeamFile): TeamMetric | null {
  let best: TeamMetric | null = null
  let size = BIG_CHANGE
  for (const side of ['off', 'def'] as const) {
    for (const m of file.units[side].live) {
      if (!m.observed || !m.team_last) continue
      const d = Math.abs(m.observed.pct - m.team_last.pct)
      if (d >= size) {
        best = m
        size = d
      }
    }
  }
  return best
}

/** A within-season share as an approximate place among `of` teams: 0.98 of 32 is about 1st. */
export const placeOf = (pct: number, of = 32) => Math.min(of, Math.max(1, Math.round((1 - pct) * of + 0.5)))

export function fmtRate(v: number, unit: string): string {
  if (unit === 'seconds') return `${v.toFixed(2)} s`
  if (unit === 'epa') return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
  return `${(100 * v).toFixed(1)}%`
}

/** "Weeks 2–4, 7" from a list of weeks. */
export function weekList(weeks: number[]): string {
  const runs: [number, number][] = []
  for (const w of [...weeks].sort((a, b) => a - b)) {
    const last = runs.at(-1)
    if (last && w === last[1] + 1) last[1] = w
    else runs.push([w, w])
  }
  return `Week${weeks.length > 1 ? 's' : ''} ${runs.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(', ')}`
}

/** Who started when the Week 1 starter didn't: one line per quarterback. */
export function starterLines(file: TeamFile): string[] {
  const by = new Map<string, number[]>()
  for (const s of file.other_starter_weeks) by.set(s.qb, [...(by.get(s.qb) ?? []), s.week])
  return [...by].map(([qb, weeks]) => `${qb} started ${weekList(weeks)}.`)
}
