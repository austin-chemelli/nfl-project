/** Summary-strip tiles for the team page (ADR 0017, 0022): pure functions of the files, each null when it can't be stated. */
import type { LeagueFile, UnitCaller, TeamFile, TeamRow } from '../../data/contract'
import { ordinal } from '../league/helpers'
import { fmtProb } from '../league/playoffs'
import { biggestChange } from './tendencies'

export type TileText = { label: string; value: string; sub: string; tab: string }

export function playoffTile(league: LeagueFile | undefined, code: string): TileText | null {
  const odds = league?.odds.student.teams[code]
  if (!odds) return null
  const seed = league?.teams.find((t) => t.team === code)?.seed_today
  return { label: 'Playoff chance', value: fmtProb(odds.playoffs), sub: seed ? `Seed ${seed} today` : 'Outside the seeds today', tab: 'overview' }
}

const SHORT: Record<string, string> = {
  same_caller: 'Same as last season',
  same_caller_new_qb: 'New starting quarterback',
  took_over: 'Took over from inside',
  moved_team: 'New play-caller here',
  promoted_first_time: 'First NFL year calling, promoted',
  outside_first_time: 'First year calling NFL plays',
}

export function callerTile(caller: UnitCaller | null | undefined, side: 'off' | 'def', since?: number): TileText | null {
  if (!caller) return null
  const unit = side === 'off' ? 'offense' : 'defense'
  if (!caller.confirmed) return { label: `Runs the ${unit}`, value: caller.name, sub: 'Play-caller not confirmed', tab: 'staff' }
  const sub = since ? `Took over in Week ${since}` : caller.situation ? SHORT[caller.situation] : caller.is_head_coach ? 'The head coach' : ''
  return { label: `Calls the ${unit}`, value: caller.name, sub: sub ?? '', tab: 'staff' }
}

export function changeTile(file: TeamFile | undefined): TileText | null {
  const m = file && biggestChange(file)
  if (!m?.observed || !m.team_last) return null
  return { label: 'Biggest change', value: m.label, sub: `${ordinal(m.team_last.rank)} last year, ${ordinal(m.observed.rank)} now`, tab: 'tendencies' }
}

export function nextGameTile(row: TeamRow | undefined): TileText | null {
  const g = row?.games.find((x) => x.id === row.next_game_id)
  if (!g) return null
  return { label: 'Next game', value: `${g.home ? 'vs' : '@'} ${g.opp}`, sub: `Week ${g.week}`, tab: 'games' }
}
