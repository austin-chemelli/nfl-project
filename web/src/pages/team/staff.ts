import type { TeamFile } from '../../data/contract'
import { ordinal } from '../league/helpers'
import { placeOf } from './tendencies'

export type Side = 'off' | 'def'
type Spell = TeamFile['staff']['current'][number]
type Change = TeamFile['staff']['changes'][number]
type Caller = NonNullable<TeamFile['units']['off']['caller']>

const EVIDENCE: Record<string, string> = { official: 'Team site', news: 'News', roundup: '32-team list' }
const COORD = { off: 'Offensive coordinator', def: 'Defensive coordinator' } as const

/** The link label for an evidence kind; null for one we don't know. */
export function evidenceLabel(evidence: string | null | undefined): string | null {
  return evidence ? (EVIDENCE[evidence] ?? null) : null
}

export function callerTitle(c: Caller, side: Side): string {
  return c.is_head_coach ? 'Head coach' : COORD[side]
}

/** "MIA 2022–25, LAC 2026"; a one-season stint prints its year once. */
export function careerLine(career: Caller['career']): string {
  return career
    .map((s) => (s.from === s.to ? `${s.team} ${s.from}` : `${s.team} ${s.from}–${String(s.to).slice(-2)}`))
    .join(', ')
}

const sideOf = (role: string): Side | null =>
  role === 'OC' || role === 'OFF_PC' ? 'off' : role === 'DC' || role === 'DEF_PC' ? 'def' : null

/** Head coach first, then coordinators not already named on a caller card; nobody twice. */
export function otherStaff(file: TeamFile): (Spell & { title: string })[] {
  const seen = new Set<string>()
  for (const side of ['off', 'def'] as const) {
    const c = file.units[side].caller
    if (c) seen.add(c.name)
  }
  const rank = (r: string) => (r === 'HC' ? 0 : r === 'OC' ? 1 : 2)
  const rows = file.staff.current.filter((s) => s.role === 'HC' || s.role === 'OC' || s.role === 'DC').sort((a, b) => rank(a.role) - rank(b.role))
  const out: (Spell & { title: string })[] = []
  for (const s of rows) {
    if (seen.has(s.name)) continue
    seen.add(s.name)
    const title = s.role === 'HC' ? 'Head coach' : s.role === 'OC' ? COORD.off : COORD.def
    out.push({ ...s, title })
  }
  return out
}

export type ChangeLine = { week: number; text: string }

/** One line per person, week and side: a title change and a play-calling change together read as one. */
export function changeLines(changes: Change[]): ChangeLine[] {
  const groups = new Map<string, Change[]>()
  for (const c of changes) {
    const key = `${c.start_week}|${c.name}|${c.role === 'HC' ? 'hc' : (sideOf(c.role) ?? c.role)}`
    groups.set(key, [...(groups.get(key) ?? []), c])
  }
  const lines: ChangeLine[] = []
  for (const rows of groups.values()) {
    const first = rows[0]
    const week = first.start_week
    const side = sideOf(first.role)
    if (!side) {
      if (first.role === 'HC') lines.push({ week, text: `Week ${week}: ${first.name} became head coach` })
      continue
    }
    const title = rows.find((r) => r.role === 'OC' || r.role === 'DC')
    const pc = rows.find((r) => r.role === 'OFF_PC' || r.role === 'DEF_PC')
    const from = title?.replaced ?? pc?.replaced ?? null
    const fromText = from ? ` from ${from}` : ''
    const unit = side === 'off' ? 'offense' : 'defense'
    let text: string
    if (title && pc) text = `took over the ${unit}${fromText}`
    else if (pc) text = `took over the ${side === 'off' ? 'offensive' : 'defensive'} play-calling${fromText}`
    else text = `became ${COORD[side].toLowerCase()}${from ? `, replacing ${from}` : ''}`
    lines.push({ week, text: `Week ${week}: ${first.name} ${text}` })
  }
  return lines.sort((a, b) => a.week - b.week)
}

type Trait = Caller['traits'][number]

const yearSpan = (first: number, last?: number) => (last == null || last === first ? `${first}` : `${first}–${String(last).slice(-2)}`)

/** "More pre-snap motion than most: about the highest, in each of 4 seasons calling plays (2022–25)." */
export function traitLine(t: Trait): string {
  const high = t.pct >= 0.5
  const word = high ? t.hi : t.lo
  const label = /^[A-Z][a-z]/.test(t.label) ? t.label.charAt(0).toLowerCase() + t.label.slice(1) : t.label
  const n = high ? placeOf(t.pct) : 33 - placeOf(t.pct)
  const where = n === 1 ? `the ${high ? 'highest' : 'lowest'}` : `${ordinal(n)}-${high ? 'highest' : 'lowest'}`
  const seasons = t.seasons === 1 ? 'in his season' : `in each of ${t.seasons} seasons`
  return `${word.charAt(0).toUpperCase()}${word.slice(1)} ${label} than most: about ${where} on average, ${seasons} calling plays (${yearSpan(t.first, t.last)}).`
}

